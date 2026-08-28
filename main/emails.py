"""
Shared helpers for rendering and sending branded HTML transaction emails.

Every service that emails a user goes through :func:`render_email` +
:func:`send_branded_mail` so the design and the link-building stay in one
place. Links are always absolute and rooted at ``settings.SITE_BASE_URL``
(localhost in development, a real domain in production).
"""

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


def absolute_url(path="/"):
    """Join ``path`` onto the configured site base URL (never doubles slashes)."""
    base = settings.SITE_BASE_URL
    if not path:
        return base
    return f"{base}/{path.lstrip('/')}"


def send_branded_mail(subject, text, recipient_list, template, context=None):
    """
    Send a plain-text fallback plus a branded HTML rendering of ``template``.

    ``text`` stays as the email body for plain-text clients; ``template``
    receives ``context`` plus a ``subject`` key for the HTML wrapper.
    """
    ctx = dict(context or {})
    ctx.setdefault("subject", subject)
    html = render_to_string(template, ctx)
    return send_mail(
        subject=subject,
        message=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipient_list,
        html_message=html,
    )
