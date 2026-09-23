"""
CV generator views: builder/selector screen, per-skin inline A4 PDF preview
and PDF export via WeasyPrint. Only certified facts ever reach a CV.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from accounts.models import CvTemplate

from .engine import (
    CV_LANGS,
    CV_SKINS,
    cv_context_from_user,
    demo_cv_context,
    render_cv_docx,
    render_cv_html,
    template_completeness,
)

WORLD_BANK_COMPLETENESS_FIELDS = {
    "identity": "Identité",
    "skills": "Compétences",
    "trainings": "Formation",
    "projects": "Projets",
    "positions": "Postes",
    "languages": "Langues",
    "bio": "Profil",
    "strengths": "Points forts",
    "indicators_list": "Indicateurs certifiés",
    "expertise_domains": "Domaines d'expertise",
    "other_trainings": "Autres formations",
    "associations": "Associations et mandats",
    "publications": "Publications",
    "teaching": "Enseignement",
    "media": "Médias",
    "miscellaneous": "Divers",
}


def _lang(request):
    lang = request.GET.get("lang", "fr")
    return lang if lang in CV_LANGS else "fr"


def _selection_from_request(request):
    selection = {}
    for key in ("projects", "positions", "publications", "teaching", "media"):
        values = set()
        for raw_value in request.GET.getlist(key):
            for item in raw_value.split(","):
                item = item.strip()
                if item.isdigit():
                    values.add(int(item))
        if values:
            selection[key] = values
    return selection or None


def _querystring_without_lang(request):
    query = request.GET.copy()
    query.pop("lang", None)
    return query.urlencode()


def _context_for(request, lang):
    if request.GET.get("example"):
        return demo_cv_context(lang)
    return cv_context_from_user(request.user, lang, selection=_selection_from_request(request))


@login_required
def cv_builder(request):
    """Selector screen: three skins, preview + PDF links."""
    lang = _lang(request)
    selection_query = _querystring_without_lang(request)
    selection = _selection_from_request(request) or {}
    skins = [
        {
            "key": key,
            "meta": meta,
            "preview": f"/cv/{key}/" + (f"?{selection_query}" if selection_query else ""),
            "pdf": f"/cv/{key}/pdf/" + (f"?{selection_query}" if selection_query else ""),
            "docx": f"/cv/{key}/docx/" + (f"?{selection_query}" if selection_query else ""),
        }
        for key, meta in CV_SKINS.items()
    ]
    profile = request.user.expert_profile
    confirmed_projects = []
    seen_project_ids = set()
    for contribution in profile.confirmed_contributions():
        project = contribution.project
        if project.id in seen_project_ids:
            continue
        seen_project_ids.add(project.id)
        confirmed_projects.append(project)
    return render(
        request,
        "cv/builder.html",
        {
            "skins": skins,
            "lang": lang,
            "profile": profile,
            "template_choices": CvTemplate.choices,
            "available_projects": confirmed_projects,
            "available_positions": profile.positions.all(),
            "available_publications": profile.publications.all(),
            "selected_projects": selection.get("projects", set()),
            "selected_positions": selection.get("positions", set()),
            "selected_publications": selection.get("publications", set()),
            "selected_querystring": selection_query,
            "world_bank_completion": {
                **template_completeness(cv_context_from_user(request.user, lang), "world_bank_new"),
                "required_labels": [
                    WORLD_BANK_COMPLETENESS_FIELDS[field]
                    for field in template_completeness(
                        cv_context_from_user(request.user, lang), "world_bank_new"
                    )["missing"]
                ],
                "recommended_labels": [
                    WORLD_BANK_COMPLETENESS_FIELDS[field]
                    for field in template_completeness(
                        cv_context_from_user(request.user, lang), "world_bank_new"
                    )["recommended_missing"]
                ],
            },
        },
    )


@login_required
def cv_preview(request, skin):
    """Inline A4 PDF preview of one skin (HTML fallback for print/debug)."""
    if skin not in CV_SKINS:
        messages.error(request, _("Modèle de CV inconnu."))
        return redirect("cv_generator:builder")

    lang = _lang(request)
    html = render_cv_html(_context_for(request, lang), skin, lang)

    if request.GET.get("format") != "html":
        try:
            from weasyprint import HTML

            pdf = HTML(string=html, base_url="").write_pdf()
        except ImportError:
            pdf = None
        if pdf is not None:
            response = HttpResponse(pdf, content_type="application/pdf")
            name = request.user.get_full_name() or request.user.username
            filename = f"CV_{name.replace(' ', '_')}_{skin}_apercu.pdf"
            response["Content-Disposition"] = f'inline; filename="{filename}"'
            return response

    return HttpResponse(html)


@login_required
def cv_pdf(request, skin):
    """PDF export through WeasyPrint (falls back to the print view)."""
    if skin not in CV_SKINS:
        messages.error(request, _("Modèle de CV inconnu."))
        return redirect("cv_generator:builder")

    lang = _lang(request)
    try:
        from weasyprint import HTML

        pdf = HTML(
            string=render_cv_html(_context_for(request, lang), skin, lang),
            base_url="",
        ).write_pdf()
    except ImportError:
        messages.warning(
            request,
            _("Moteur PDF indisponible sur ce serveur : ouvrez plutôt la vue d'impression."),
        )
        return redirect("cv_generator:preview", skin=skin)

    response = HttpResponse(pdf, content_type="application/pdf")
    name = request.user.get_full_name() or request.user.username
    filename = f"CV_{name.replace(' ', '_')}_{skin}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def cv_docx(request, skin):
    """Editable Word export from the same CV context as HTML/PDF (T10)."""
    if skin not in CV_SKINS:
        messages.error(request, _("Modèle de CV inconnu."))
        return redirect("cv_generator:builder")

    lang = _lang(request)
    docx = render_cv_docx(_context_for(request, lang), skin, lang)
    response = HttpResponse(
        docx,
        content_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    )
    name = request.user.get_full_name() or request.user.username
    filename = f"CV_{name.replace(' ', '_')}_{skin}.docx"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
