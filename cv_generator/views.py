"""
CV generator views: builder/selector screen, per-skin preview (HTML) and
PDF export via WeasyPrint. Only certified facts ever reach a CV.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from accounts.models import CvTemplate

from .engine import CV_LANGS, CV_SKINS, cv_context_from_user, demo_cv_context, render_cv_html


def _lang(request):
    lang = request.GET.get("lang", "en")
    return lang if lang in CV_LANGS else "en"


def _context_for(request, lang):
    if request.GET.get("example"):
        return demo_cv_context(lang)
    return cv_context_from_user(request.user, lang)


@login_required
def cv_builder(request):
    """Selector screen: three skins × two languages, preview + PDF links."""
    lang = _lang(request)
    skins = [
        {
            "key": key,
            "meta": meta,
            "preview": f"/cv/{key}/?lang={lang}",
            "pdf": f"/cv/{key}/pdf/?lang={lang}",
        }
        for key, meta in CV_SKINS.items()
    ]
    profile = request.user.expert_profile
    return render(
        request,
        "cv/builder.html",
        {
            "skins": skins,
            "lang": lang,
            "langs": CV_LANGS,
            "profile": profile,
            "template_choices": CvTemplate.choices,
        },
    )


@login_required
def cv_preview(request, skin):
    """Standalone HTML preview of one skin."""
    if skin not in CV_SKINS:
        messages.error(request, _("Unknown CV template."))
        return redirect("cv_generator:builder")
    html = render_cv_html(_context_for(request, _lang(request)), skin, _lang(request))
    return HttpResponse(html)


@login_required
def cv_pdf(request, skin):
    """PDF export through WeasyPrint (falls back to the print view)."""
    if skin not in CV_SKINS:
        messages.error(request, _("Unknown CV template."))
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
            _("PDF engine unavailable on this server: open the print view instead."),
        )
        return redirect("cv_generator:preview", skin=skin)

    response = HttpResponse(pdf, content_type="application/pdf")
    name = request.user.get_full_name() or request.user.username
    filename = f"CV_{name.replace(' ', '_')}_{skin}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
