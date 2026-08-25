"""
Multi-skin CV engine (Epic 7).

One canonical context built ONLY from certified facts (cross-confirmed
contributions), rendered through three institutional skins:

* ``academic_harvard_mit``: serif, publication-list styling
* ``afd``                 : Agence Française de Développement look
* ``world_bank``          : World Bank consultancy look

Each skin is a self-contained Django template (embedded CSS) usable both for
browser preview and WeasyPrint PDF export. French and English are supported
through explicit label dictionaries (no runtime translation dependency).
"""

from datetime import date

from django.template.loader import render_to_string

from certification.models import ContributionStatus

CV_SKINS = {
    "academic_harvard_mit": {
        "name": "Academic: Harvard/MIT",
        "description": "Serif, publication-grade layout for research and academic applications.",
    },
    "afd": {
        "name": "AFD",
        "description": "Agence Française de Développement consultancy format.",
    },
    "world_bank": {
        "name": "World Bank",
        "description": "World Bank short-list consulting format.",
    },
}
CV_LANGS = ("fr", "en")

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

LABELS = {
    "fr": {
        "curriculum": "Curriculum vitæ",
        "certified_cv": "CV certifié: expériences confirmées par double déclaration",
        "professional_id": "Identifiant professionnel permanent",
        "profile": "Profil",
        "expertise": "Domaines d'expertise",
        "trainings": "Formations",
        "experience": "Expérience professionnelle certifiée",
        "missions": "Missions & réalisations",
        "trust_score": "Indice de confiance",
        "references": "Références vérifiables sur urbantrack.africa",
        "generated_on": "Généré le",
        "ongoing": "en cours",
        "client": "Client",
        "page_of": "Page %(page)s / %(total)s",
    },
    "en": {
        "curriculum": "Curriculum vitæ",
        "certified_cv": "Certified CV: experience confirmed by cross-declaration",
        "professional_id": "Permanent professional ID",
        "profile": "Profile",
        "expertise": "Areas of expertise",
        "trainings": "Education & training",
        "experience": "Certified professional experience",
        "missions": "Assignments & achievements",
        "trust_score": "Trust score",
        "references": "Verifiable references on urbantrack.africa",
        "generated_on": "Generated on",
        "ongoing": "ongoing",
        "client": "Client",
        "page_of": "Page %(page)s / %(total)s",
    },
}

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


def _experiences(user, lang):
    """Confirmed contributions only, newest first."""
    contributions = (
        user.contributions.filter(status=ContributionStatus.CONFIRMED)
        .select_related("project")
        .order_by("-project__duration_start")
    )
    return [
        {
            "title": c.project.official_name,
            "client": c.project.client_name,
            "role": _role_label(c.role_type, lang),
            "period": _period(c.project, lang),
            "bullets": c.contribution_bullets_lines,
        }
        for c in contributions
    ]


def cv_context_from_user(user, lang):
    """Canonical CV context from a real expert account."""
    profile = user.expert_profile
    return {
        "identity": {
            "name": user.get_full_name() or user.username,
            "professional_id": user.professional_id,
            "headline": profile.headline,
            "email": user.email,
            "city": profile.city,
            "country": profile.country,
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
        "template_choice": profile.cv_template,
        "experiences": _experiences(user, lang),
        "trust_score": profile.trust_score(),
        "is_demo": False,
    }


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
        "is_demo": True,
    }


def render_cv_html(context, skin_key, lang):
    """Render one fully self-contained HTML document for preview/PDF."""
    if skin_key not in CV_SKINS or lang not in CV_LANGS:
        raise ValueError(f"unknown skin/lang: {skin_key}/{lang}")
    return render_to_string(
        f"cv/{skin_key}.html",
        {
            "cv": context,
            "labels": LABELS[lang],
            "lang": lang,
            "skin": skin_key,
            "today": date.today().strftime("%d/%m/%Y" if lang == "fr" else "%b %d, %Y"),
        },
    )
