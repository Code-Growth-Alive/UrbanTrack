import json
import logging
from datetime import date
from io import BytesIO
from pathlib import Path

from django.template.loader import render_to_string

from certification.models import ContributionStatus

logger = logging.getLogger(__name__)

# T18: one shared, canonical label dictionary for every CV template, living in
# docs/cv-labels.i18n.json (single source of truth). `LABELS` is loaded from it;
# templates never hard-code a label. Missing keys fall back to English with a
# logged warning — never a raw key, never broken text.
FALLBACK_LANG = "en"
_LABELS_PATH = Path(__file__).resolve().parents[1] / "docs" / "cv-labels.i18n.json"


def load_cv_labels():
    """Load the shared FR/EN label dictionary from disk."""
    with _LABELS_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    labels = {
        lang: dict(raw[lang])
        for lang in raw["_supported_langs"]
        if lang != "_fallback_lang" and lang != "_supported_langs"
    }
    if FALLBACK_LANG not in labels:
        raise RuntimeError(f"cv-labels.i18n.json is missing the {FALLBACK_LANG!r} dictionary")
    return labels


class LabelResolver(dict):
    """
    Read-only label table handed to the templates.

    T18 requirement: when a label is missing in the requested language, the
    English value is used and a warning is logged — never a raw key, never
    broken text. The merge happens eagerly (fallback first, requested language
    overrides it), because Django templates only call ``__getitem__`` for keys
    already contained in a mapping.
    """

    def __init__(self, lang, current, fallback):
        missing = set(fallback) - set(current)
        super().__init__({**fallback, **current})
        for key in sorted(missing):
            logger.warning(
                "CV label %r missing in %s — falling back to %s",
                key,
                lang,
                FALLBACK_LANG,
            )

    def __getitem__(self, key):
        if key not in self:
            raise KeyError(key)
        return dict.__getitem__(self, key)


CV_SKINS = {
    "world_bank_new": {
        "name": "Banque mondiale",
        "description": "Format Banque mondiale détaillé selon les 18 rubriques de référence.",
    },
    "academic_harvard_mit": {
        "name": "Académique : Harvard/MIT",
        "description": "Mise en page serif sobre pour les candidatures académiques et"
        " de recherche.",
    },
    "afd": {
        "name": "AFD",
        "description": "Format de consultation de l'Agence Française de Développement.",
    },
}
CV_LANGS = ("fr", "en")

# T20: per-template data contract — the source of truth for the shape of the
# ``cv`` object each template expects. ``validate_cv_context`` enforces it at
# render time (explicit errors instead of silently incomplete output); T19
# reuses the field list for completeness checks.
_CV_SUPPORTED_TYPES = {
    "str": str,
    "nullable-str": (str, type(None)),
    "int": int,
    "bool": bool,
    "list": list,
    "dict": dict,
    "nullable-dict": (dict, type(None)),
}

_CLASSIC_SKIN_FIELDS = (
    ("identity", "dict", True),
    ("bio", "nullable-str", True),
    ("skills", "list", True),
    ("trainings", "list", True),
    ("strengths", "list", True),
    ("countries", "list", True),
    ("languages", "list", True),
    ("misc", "str", True),
    ("declared", "dict", True),
    ("has_declared", "bool", True),
    ("template_choice", "nullable-str", True),
    ("experiences", "list", True),
    ("trust_score", "int", True),
    ("indicators", "dict", True),
    ("is_demo", "bool", True),
)

CV_CONTRACTS = {
    skin: {field: (expected, required) for field, expected, required in _CLASSIC_SKIN_FIELDS}
    for skin in ("academic_harvard_mit", "afd")
}
# T17 v2 template (world_bank_new.html, 18 sections) — fills several blocks
# with dedicated fields instead of the single legacy "declared" dict.
CV_CONTRACTS["world_bank_new"] = {
    "identity": ("dict", True),
    "bio": ("nullable-str", True),
    "strengths": ("list", True),
    "indicators_list": ("list", True),
    "expertise_domains": ("list", True),
    "skills": ("list", True),
    "trainings": ("list", True),
    "other_trainings": ("list", True),
    "associations": ("list", True),
    "countries": ("list", True),
    "languages": ("list", True),
    "positions": ("list", True),
    "projects": ("list", True),
    "publications": ("list", True),
    "teaching": ("dict", True),
    "media": ("list", True),
    "miscellaneous": ("list", True),
    "certification": ("nullable-dict", True),
    "trust_score": ("int", True),
    "is_demo": ("bool", True),
}


class CvContextError(ValueError):
    """A CV context violates its template's data contract (T20)."""


def _has_content(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_content(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_content(item) for item in value)
    return True


CV_COMPLETENESS_RULES = {
    "world_bank_new": {
        "required": [
            "identity",
            "skills",
            "trainings",
            "projects",
            "positions",
            "languages",
        ],
        "recommended": [
            "bio",
            "strengths",
            "indicators_list",
            "expertise_domains",
            "other_trainings",
            "associations",
            "publications",
            "teaching",
            "media",
            "miscellaneous",
        ],
    }
}


def validate_cv_context(context, template_key):
    """
    Enforce the data contract of a CV template with explicit, readable errors
    (T20): a missing required field, a wrong-typed field or an unknown template
    raise ``CvContextError`` instead of rendering silently broken output.
    """
    if template_key not in CV_CONTRACTS:
        raise CvContextError(
            f"No data contract registered for CV template {template_key!r} — "
            "register one in cv_generator.engine.CV_CONTRACTS (T20)."
        )
    for field, (expected, required) in CV_CONTRACTS[template_key].items():
        if field not in context:
            if required:
                raise CvContextError(
                    f"{template_key}: CV context is missing required field {field!r}."
                )
            continue
        value = context[field]
        if not isinstance(value, _CV_SUPPORTED_TYPES[expected]):
            raise CvContextError(
                f"{template_key}: CV context field {field!r} must be {expected} "
                f"(got {type(value).__name__})."
            )
    return True


def template_completeness(context, template_key):
    """Return a simple completeness summary for a given CV template."""
    rules = CV_COMPLETENESS_RULES.get(template_key)
    if not rules:
        return {"percent": 100, "missing": [], "recommended_missing": []}

    required = rules["required"]
    recommended = rules["recommended"]
    missing = [field for field in required if not _has_content(context.get(field))]
    recommended_missing = [field for field in recommended if not _has_content(context.get(field))]
    total = len(required) + len(recommended)
    present = total - len(missing) - len(recommended_missing)
    percent = round((present / total) * 100) if total else 100
    return {
        "percent": percent,
        "missing": missing,
        "recommended_missing": recommended_missing,
    }


ROLE_LABELS = {
    # Mirrors certification.RoleType but decoupled from DB choices for FR/EN.
    "director": {"fr": "Directeur / Directrice de projet", "en": "Project Director"},
    "manager": {"fr": "Chef / Cheffe de projet", "en": "Project Manager"},
    "assistant": {"fr": "Assistant(e)", "en": "Assistant"},
    "specialist": {"fr": "Spécialiste", "en": "Specialist"},
    "consultant": {"fr": "Consultant(e)", "en": "Consultant"},
    "engineer": {"fr": "Ingénieur(e)", "en": "Engineer"},
    "other": {"fr": "Autre contribution", "en": "Other contribution"},
}

# T18: unique, shared label dictionary — loaded from docs/cv-labels.i18n.json.
LABELS = load_cv_labels()

DEMO_EXPERT = {
    "first_name": "Aminata",
    "last_name": "Sow",
    "email": "aminata.sow@example.com",
    "city": "Dakar",
    "country": "Senegal",
}


def _role_label(role_type, lang):
    return ROLE_LABELS.get(role_type, ROLE_LABELS["other"])[lang]


def _period(project, lang):
    start = project.duration_start.strftime("%m/%Y")
    end = (
        project.duration_end.strftime("%m/%Y") if project.duration_end else LABELS[lang]["ongoing"]
    )
    return f"{start} – {end}"


def _year_period(year_start, year_end, lang):
    if not year_start and not year_end:
        return ""
    if year_start and not year_end:
        return f"{year_start} – {LABELS[lang]['ongoing']}"
    if year_start == year_end:
        return str(year_start)
    return f"{year_start or '?'} – {year_end or '?'}"


def _position_period(position, lang):
    if not position.date_start:
        return ""
    start = position.date_start.strftime("%m/%Y")
    end = position.date_end.strftime("%m/%Y") if position.date_end else LABELS[lang]["ongoing"]
    return f"{start} – {end}"


def _indicators(profile, lang):
    """
    T7: certified synthesis indicators, block-shaped for the skins.

    Values come from ``ExpertProfile.synthesis_indicators`` (computed from the
    confirmed contributions only). Zero-valued entries are dropped so a brand
    new account shows an empty block instead of a row of zeros.
    """
    label_keys = {
        "years_experience": "years_experience",
        "projects": "projects_certified",
        "contributions": "contributions",
        "countries": "countries_certified",
        "donor_programmes": "donor_programmes",
    }
    values = profile.synthesis_indicators()
    items = [
        {"value": values[key], "label": LABELS[lang][label_keys[key]]}
        for key in (
            "years_experience",
            "projects",
            "contributions",
            "countries",
            "donor_programmes",
        )
        if values.get(key)
    ]
    return {"values": values, "items": items, "has_indicators": bool(items)}


def _selected_ids(selection, key):
    if not selection:
        return set()
    return set(selection.get(key, set()))


def _declared_blocks(profile, lang, selection=None):
    """T4 contextual (non-certifying) CV blocks + T5 declared-marker bookkeeping.

    Everything here is self-declared by the expert. The skins render these
    sections with an explicit "declared" marker and a legend (see
    templates/cv/_declared_sections.html).
    """
    selected_positions = _selected_ids(selection, "positions")
    selected_publications = _selected_ids(selection, "publications")
    selected_teaching = _selected_ids(selection, "teaching")
    selected_media = _selected_ids(selection, "media")

    positions = [
        {
            "id": p.id,
            "employer": p.employer,
            "function": p.function,
            "period": _position_period(p, lang),
            "description": p.description,
        }
        for p in profile.positions.all()
        if not selected_positions or p.id in selected_positions
    ]
    mandates = [
        {
            "id": m.id,
            "name": m.name,
            "role": m.role,
            "period": _year_period(m.year_start, m.year_end, lang),
        }
        for m in profile.mandates.all()
    ]
    publications = [
        {"id": p.id, "title": p.title, "venue": p.venue, "year": p.year or ""}
        for p in profile.publications.all()
        if not selected_publications or p.id in selected_publications
    ]
    teaching = [
        {"id": t.id, "title": t.title, "institution": t.institution, "year": t.year or ""}
        for t in profile.teaching_entries.all()
        if not selected_teaching or t.id in selected_teaching
    ]
    media = [
        {
            "id": m.id,
            "title": m.title,
            "outlet": m.outlet,
            "year": m.year or "",
            "url": m.url,
        }
        for m in profile.media_appearances.all()
        if not selected_media or m.id in selected_media
    ]
    sections = {
        "positions": positions,
        "mandates": mandates,
        "publications": publications,
        "teaching": teaching,
        "media": media,
    }
    simple = [
        profile.strengths or [],
        profile.countries_of_intervention or [],
        profile.languages or [],
        [profile.misc] if profile.misc else [],
    ]
    has_declared = any(sections.values()) or any(simple)
    return {
        "sections": sections,
        "strengths": profile.strengths or [],
        "countries": profile.countries_of_intervention or [],
        "languages": profile.languages or [],
        "misc": profile.misc or "",
        "has_declared": has_declared,
    }


def _experiences(user, lang, selection=None):
    """Confirmed contributions only, newest first."""
    selected_projects = _selected_ids(selection, "projects")
    contributions = (
        user.contributions.filter(status=ContributionStatus.CONFIRMED)
        .select_related("project")
        .order_by("-project__duration_start")
    )
    if selected_projects:
        contributions = contributions.filter(project_id__in=selected_projects)
    return [
        {
            "project_id": c.project_id,
            "title": c.project.official_name,
            "client": c.project.client_name,
            "country": c.project.country.name if c.project.country else "",
            "role": _role_label(c.role_type, lang),
            "period": _period(c.project, lang),
            "bullets": c.contribution_bullets_lines,
            "status": "confirmed",
        }
        for c in contributions
    ]


def user_identity(user, profile):
    return {
        "name": user.get_full_name() or user.username,
        "professional_id": user.professional_id,
        "headline": profile.headline,
        "email": user.email,
        "city": profile.city,
        "country": profile.country,
    }


def _world_bank_context(profile, user, declared, experiences, indicators_items):
    skills = [skill.name for skill in profile.skills.all()]
    publications = [
        {
            "authors": user.get_full_name() or user.username,
            "year": publication.year or "",
            "title": publication.title,
            "venue": publication.venue,
        }
        for publication in profile.publications.all()
    ]
    teaching = {
        "masters": [
            {
                "title": training.title,
                "institution": training.institution,
                "role": "",
            }
            for training in profile.trainings.all()
        ],
        "certificates": [],
        "thesis_supervision": profile.misc or "",
        "moocs": [],
        "courses": [
            {
                "title": entry.title,
                "institution": entry.institution,
                "role": "",
            }
            for entry in profile.teaching_entries.all()
        ],
    }
    positions = [
        {
            "period": row["period"],
            "employer": row["employer"],
            "function": row["function"],
            "country": "",
            "description": row["description"],
            "status": "declared",
        }
        for row in declared["sections"]["positions"]
    ]
    projects = [
        {
            "dates": experience["period"],
            "country": experience.get("country", ""),
            "title": experience["title"],
            "role": experience["role"],
            "description": "\n".join(experience.get("bullets", [])),
            "status": experience.get("status", "confirmed"),
        }
        for experience in experiences
    ]
    return {
        "identity": {
            **user_identity(user, profile),
            "birth_date": profile.birth_date.strftime("%d/%m/%Y") if profile.birth_date else "",
            "nationality": profile.nationality,
            "linkedin": "",
        },
        "bio": profile.bio,
        "strengths": declared["strengths"],
        "indicators_list": indicators_items,
        "expertise_domains": [{"family": "Compétences", "items": ", ".join(skills)}]
        if skills
        else [],
        "skills": skills,
        "trainings": [
            {
                "degree": training.title,
                "institution": training.institution,
                "year": training.year or "",
            }
            for training in profile.trainings.all()
        ],
        "other_trainings": [],
        "associations": [
            {
                "role": mandate.role,
                "entity": mandate.name,
                "since": str(mandate.year_start) if mandate.year_start else "",
            }
            for mandate in profile.mandates.all()
        ],
        "countries": declared["countries"],
        "languages": [
            {
                "name": language.get("name", ""),
                "read": language.get("read", ""),
                "spoken": language.get("spoken", ""),
                "writing": language.get("written", ""),
            }
            for language in declared["languages"]
        ],
        "positions": positions,
        "projects": projects,
        "publications": publications,
        "teaching": teaching,
        "media": [
            {
                "title": media.title,
                "outlet": media.outlet,
                "date": str(media.year or ""),
            }
            for media in profile.media_appearances.all()
        ],
        "miscellaneous": [profile.misc] if profile.misc else [],
        "certification": None,
        "trust_score": profile.trust_score(),
        "is_demo": False,
    }


def cv_context_from_user(user, lang, selection=None):
    """Canonical CV context from a real expert account."""
    profile = user.expert_profile
    declared = _declared_blocks(profile, lang, selection=selection)
    indicators = _indicators(profile, lang)
    context = {
        "identity": {
            "name": user.get_full_name() or user.username,
            "professional_id": user.professional_id,
            "headline": profile.headline,
            "email": user.email,
            "city": profile.city,
            "country": profile.country,
            "nationality": profile.nationality,
            "phone": profile.phone,
        },
        "bio": profile.bio,
        "skills": [skill.name for skill in profile.skills.all()],
        "trainings": [
            {
                "degree": t.title,
                "institution": t.institution,
                "year": t.year or "",
            }
            for t in profile.trainings.all()
        ],
        "strengths": declared["strengths"],
        "countries": declared["countries"],
        "languages": declared["languages"],
        "misc": declared["misc"],
        "declared": declared["sections"],
        "has_declared": declared["has_declared"],
        "template_choice": profile.cv_template,
        "experiences": _experiences(user, lang, selection=selection),
        "trust_score": profile.trust_score(),
        "indicators": indicators,
        "indicators_list": indicators["items"],
        "is_demo": False,
    }
    context.update(
        _world_bank_context(
            profile,
            user,
            declared,
            context["experiences"],
            indicators["items"],
        )
    )
    return context


def demo_cv_context(lang="en"):
    """Rich sample context powering the on-site examples."""
    return {
        "identity": {
            "name": "Aminata Sow",
            "professional_id": "OX-2025-0042",
            "headline": "Urban planner: resilient secondary cities"
            if lang == "en"
            else "Urbaniste: villes secondaires résilientes",
            "email": DEMO_EXPERT["email"],
            "city": DEMO_EXPERT["city"],
            "country": DEMO_EXPERT["country"],
        },
        "indicators": {
            "values": {
                "years_experience": 12,
                "projects": 14,
                "contributions": 18,
                "countries": 4,
                "donor_programmes": 6,
            },
            "items": [
                {"value": 12, "label": LABELS[lang]["years_experience"]},
                {"value": 14, "label": LABELS[lang]["projects_certified"]},
                {"value": 18, "label": LABELS[lang]["contributions"]},
                {"value": 4, "label": LABELS[lang]["countries_certified"]},
                {"value": 6, "label": LABELS[lang]["donor_programmes"]},
            ],
            "has_indicators": True,
        },
        "indicators_list": [
            {"value": 12, "label": LABELS[lang]["years_experience"]},
            {"value": 14, "label": LABELS[lang]["projects_certified"]},
            {"value": 18, "label": LABELS[lang]["contributions"]},
            {"value": 4, "label": LABELS[lang]["countries_certified"]},
            {"value": 6, "label": LABELS[lang]["donor_programmes"]},
        ],
        "bio": (
            "Urban planner with twelve years of experience in urban renewal, "
            "sanitation and mobility across West Africa. Certified lead on "
            "donor-financed programmes (World Bank, AFD, EU)."
            if lang == "en"
            else (
                "Urbaniste avec douze ans d'expérience en renouvellement "
                "urbain, assainissement et mobilité en Afrique de l'Ouest. "
                "Cheffe certifiée de programmes bailleurs (Banque mondiale, "
                "AFD, UE)."
            )
        ),
        "skills": [
            [
                "Urban planning",
                "Sanitation engineering",
                "Resilience strategy",
                "Feasibility studies",
                "Donor reporting",
                "GIS analysis",
            ],
            [
                "Planification urbaine",
                "Ingénierie de l'assainissement",
                "Stratégie de résilience",
                "Études de faisabilité",
                "Reporting bailleurs",
                "Analyse SIG",
            ],
        ][0 if lang == "en" else 1],
        "trainings": [
            {
                "degree": "MSc Urban Engineering",
                "institution": "Ecole Polytechnique Fédérale de Lausanne",
                "year": "2012",
            },
            {
                "degree": "BSc Civil Engineering",
                "institution": "Université Cheikh Anta Diop, Dakar",
                "year": "2009",
            },
        ],
        "experiences": [
            {
                "title": "Dakar Corniche Ouest redevelopment",
                "client": "City of Dakar",
                "role": ROLE_LABELS["manager"][lang],
                "period": "03/2023 – ongoing",
                "bullets": [
                    "Led the 12 km coastal redevelopment master plan.",
                    "Coordinated 4 engineering firms and public consultations.",
                ]
                if lang == "en"
                else [
                    "Pilotage du plan directeur de réaménagement du littoral (12 km).",
                    "Coordination de 4 bureaux d'études et des consultations publiques.",
                ],
            },
            {
                "title": "Regional sanitation programme: Petite Côte",
                "client": "Ministry of Hydraulics",
                "role": ROLE_LABELS["specialist"][lang],
                "period": "01/2020 – 12/2022",
                "bullets": [
                    "Designed sanitation solutions for 14 coastal towns.",
                    "Prepared donor appraisal documentation (AFD format).",
                ]
                if lang == "en"
                else [
                    "Conception de solutions d'assainissement pour 14 communes côtières.",
                    "Préparation des documents d'évaluation bailleurs (format AFD).",
                ],
            },
        ],
        "trust_score": 87,
        "template_choice": "afd",
        "is_demo": True,
        "strengths": [
            "Urban planning",
            "Sanitation engineering",
            "Resilience strategy",
            "Donor reporting",
        ]
        if lang == "en"
        else [
            "Planification urbaine",
            "Ingénierie de l'assainissement",
            "Stratégie de résilience",
            "Reporting bailleurs",
        ],
        "countries": ["Senegal", "Mali", "Burkina Faso", "Benin"]
        if lang == "en"
        else ["Sénégal", "Mali", "Burkina Faso", "Bénin"],
        "languages": [
            {"name": "French", "read": "native", "spoken": "native", "written": "native"},
            {"name": "English", "read": "fluent", "spoken": "fluent", "written": "fluent"},
            {"name": "Wolof", "read": "basic", "spoken": "fluent", "written": "basic"},
        ],
        "misc": "",
        "declared": {
            "positions": [
                {
                    "employer": "Ministère de l'Urbanisme, Sénégal",
                    "function": "Conseillère technique",
                    "period": "01/2018 – %s" % ("ongoing" if lang == "en" else "en cours"),
                    "description": (
                        "Advisor on the national programme for resilient secondary cities."
                        if lang == "en"
                        else "Conseil au programme national des villes secondaires résilientes."
                    ),
                },
                {
                    "employer": "Groupe CICAD",
                    "function": "Cheffe de projet senior",
                    "period": "09/2013 – 12/2017",
                    "description": (
                        "Urban development projects in West and Central Africa."
                        if lang == "en"
                        else "Projets d'urbanisme en Afrique de l'Ouest et centrale."
                    ),
                },
            ],
            "mandates": [
                {
                    "name": "Ordre des urbanistes du Sénégal",
                    "role": "Membre du bureau national",
                    "period": "2021 – ongoing" if lang == "en" else "2021 – en cours",
                },
            ],
            "publications": [
                {
                    "title": "Résilience des villes secondaires en Afrique de l'Ouest",
                    "venue": "Revue africaine de l'urbanisme",
                    "year": "2023",
                },
                {
                    "title": "Shared sanitation in dense urban fabrics",
                    "venue": "Africités technical report",
                    "year": "2021",
                },
            ],
            "teaching": [
                {
                    "title": "Urban economics and local finance",
                    "institution": "Université Cheikh Anta Diop, Dakar",
                    "year": "2019",
                },
            ],
            "media": [
                {
                    "title": "La résilience des villes côtières",
                    "outlet": "RFI — science et environnement",
                    "year": "2022",
                    "url": "",
                },
            ],
        },
        "has_declared": True,
        "expertise_domains": [
            {
                "family": "Urban planning",
                "items": "Sanitation engineering, Resilience strategy, Feasibility studies",
            }
        ]
        if lang == "en"
        else [
            {
                "family": "Planification urbaine",
                "items": (
                    "Ingénierie de l'assainissement, Stratégie de résilience, Études de faisabilité"
                ),
            }
        ],
        "other_trainings": [],
        "associations": [
            {
                "role": "Board member",
                "entity": "Ordre des urbanistes du Sénégal",
                "since": "2021",
            }
        ],
        "positions": [
            {
                "period": "01/2018 – ongoing" if lang == "en" else "01/2018 – en cours",
                "employer": "Ministère de l'Urbanisme, Sénégal",
                "function": "Conseillère technique",
                "country": "Sénégal",
                "description": "Advisor on the national programme for resilient secondary cities."
                if lang == "en"
                else "Conseil au programme national des villes secondaires résilientes.",
                "status": "declared",
            },
            {
                "period": "09/2013 – 12/2017",
                "employer": "Groupe CICAD",
                "function": "Cheffe de projet senior",
                "country": "Sénégal",
                "description": "Urban development projects in West and Central Africa."
                if lang == "en"
                else "Projets d'urbanisme en Afrique de l'Ouest et centrale.",
                "status": "declared",
            },
        ],
        "projects": [
            {
                "dates": "03/2023 – ongoing" if lang == "en" else "03/2023 – en cours",
                "country": "Senegal",
                "title": "Dakar Corniche Ouest redevelopment",
                "role": ROLE_LABELS["manager"][lang],
                "description": "\n".join(
                    [
                        "Led the 12 km coastal redevelopment master plan.",
                        "Coordinated 4 engineering firms and public consultations.",
                    ]
                    if lang == "en"
                    else [
                        "Pilotage du plan directeur de réaménagement du littoral (12 km).",
                        "Coordination de 4 bureaux d'études et des consultations publiques.",
                    ]
                ),
                "status": "confirmed",
            }
        ],
        "publications": [
            {
                "authors": "Aminata Sow",
                "year": "2023",
                "title": "Résilience des villes secondaires en Afrique de l'Ouest",
                "venue": "Revue africaine de l'urbanisme",
            }
        ],
        "teaching": {
            "masters": [
                {
                    "title": "MSc Urban Engineering",
                    "institution": "Ecole Polytechnique Fédérale de Lausanne",
                    "role": "",
                }
            ],
            "certificates": [],
            "thesis_supervision": "",
            "moocs": [],
            "courses": [
                {
                    "title": "Urban economics and local finance",
                    "institution": "Université Cheikh Anta Diop, Dakar",
                    "role": "",
                }
            ],
        },
        "media": [
            {
                "title": "La résilience des villes côtières",
                "outlet": "RFI — science et environnement",
                "date": "2022",
            }
        ],
        "miscellaneous": [],
        "certification": None,
    }


def render_cv_html(context, skin_key, lang):
    """Render one fully self-contained HTML document for preview/PDF."""
    if skin_key not in CV_SKINS or lang not in CV_LANGS:
        raise ValueError(f"unknown skin/lang: {skin_key}/{lang}")
    validate_cv_context(context, skin_key)  # T20: explicit contract errors, never broken output
    return render_to_string(
        f"cv/{skin_key}.html",
        {
            "cv": context,
            "labels": LabelResolver(lang, LABELS[lang], LABELS[FALLBACK_LANG]),
            "lang": lang,
            "skin": skin_key,
            "today": date.today().strftime("%d/%m/%Y" if lang == "fr" else "%b %d, %Y"),
        },
    )


def _docx_add_section(document, title):
    document.add_heading(title, level=2)


def _docx_add_key_value(document, key, value):
    if value:
        paragraph = document.add_paragraph()
        paragraph.add_run(f"{key}: ").bold = True
        paragraph.add_run(str(value))


def _docx_add_bullets(document, values):
    for value in values:
        if value:
            document.add_paragraph(str(value), style="List Bullet")


def render_cv_docx(context, skin_key, lang):
    """
    Render an editable Word document (.docx) from the canonical CV context (T10).

    The export intentionally mirrors the HTML/PDF section structure but uses
    native Word paragraphs, headings and bullet lists, so donors can edit it in
    Word or LibreOffice without fighting a fixed-layout PDF.
    """
    if skin_key not in CV_SKINS or lang not in CV_LANGS:
        raise ValueError(f"unknown skin/lang: {skin_key}/{lang}")
    validate_cv_context(context, skin_key)

    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt

    labels = LabelResolver(lang, LABELS[lang], LABELS[FALLBACK_LANG])
    document = Document()
    for section in document.sections:
        section.top_margin = Inches(0.65)
        section.bottom_margin = Inches(0.65)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)

    styles = document.styles
    styles["Normal"].font.name = "Arial"
    styles["Normal"].font.size = Pt(10)
    for style_name in ("Title", "Heading 1", "Heading 2"):
        styles[style_name].font.name = "Arial"

    identity = context["identity"]
    title = document.add_heading(identity.get("name") or labels["curriculum"], level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.style.font.size = Pt(18)
    subtitle = document.add_paragraph(labels["certified_cv"])
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

    _docx_add_key_value(document, labels["professional_id"], identity.get("professional_id"))
    _docx_add_key_value(document, labels["expertise"], identity.get("headline"))
    _docx_add_key_value(document, "Email", identity.get("email"))
    _docx_add_key_value(document, labels["phone"], identity.get("phone"))
    location = ", ".join(
        value for value in (identity.get("city"), identity.get("country")) if value
    )
    _docx_add_key_value(document, labels["countries"], location)
    _docx_add_key_value(document, labels["nationality"], identity.get("nationality"))

    indicators = context.get("indicators", {})
    if indicators.get("items"):
        _docx_add_section(document, labels["indicators"])
        for item in indicators["items"]:
            _docx_add_key_value(document, item["label"], item["value"])

    if context.get("bio"):
        _docx_add_section(document, labels["profile"])
        document.add_paragraph(context["bio"])

    if context.get("strengths"):
        _docx_add_section(document, labels["strengths"])
        _docx_add_bullets(document, context["strengths"])

    if context.get("skills"):
        _docx_add_section(document, labels["expertise"])
        _docx_add_bullets(document, context["skills"])

    if context.get("trainings"):
        _docx_add_section(document, labels["trainings"])
        for training in context["trainings"]:
            parts = [
                training.get("degree"),
                training.get("institution"),
                str(training.get("year") or ""),
            ]
            document.add_paragraph(" — ".join(part for part in parts if part), style="List Bullet")

    if context.get("experiences"):
        _docx_add_section(document, labels["experience"])
        for experience in context["experiences"]:
            paragraph = document.add_paragraph()
            paragraph.add_run(experience["title"]).bold = True
            details = [
                experience.get("client"),
                experience.get("role"),
                experience.get("period"),
                labels["status_confirmed"],
            ]
            document.add_paragraph(" | ".join(part for part in details if part))
            _docx_add_bullets(document, experience.get("bullets", []))

    if context.get("has_declared"):
        _docx_add_section(document, f"{labels['declared']} — {labels['status_declared']}")
        document.add_paragraph(labels["declared_legend"])
        declared = context.get("declared", {})
        declared_sections = (
            ("positions", labels["positions"]),
            ("mandates", labels["mandates"]),
            ("publications", labels["publications"]),
            ("teaching", labels["teaching"]),
            ("media", labels["media"]),
        )
        for key, title_text in declared_sections:
            rows = declared.get(key) or []
            if not rows:
                continue
            document.add_heading(title_text, level=3)
            for row in rows:
                values = [str(value) for value in row.values() if value]
                document.add_paragraph(" — ".join(values), style="List Bullet")
        if context.get("countries"):
            document.add_heading(labels["countries"], level=3)
            _docx_add_bullets(document, context["countries"])
        if context.get("languages"):
            document.add_heading(labels["languages"], level=3)
            for language in context["languages"]:
                levels = [
                    f"{labels['read']}: {language.get('read')}",
                    f"{labels['spoken']}: {language.get('spoken')}",
                    f"{labels['written']}: {language.get('written')}",
                ]
                level_text = ", ".join(item for item in levels if not item.endswith(": None"))
                document.add_paragraph(
                    f"{language.get('name', '')} ({level_text})", style="List Bullet"
                )
        if context.get("misc"):
            document.add_heading(labels["misc"], level=3)
            document.add_paragraph(context["misc"])

    footer = document.sections[0].footer.paragraphs[0]
    footer.text = f"{labels['generated_on']} {date.today().isoformat()}"
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
