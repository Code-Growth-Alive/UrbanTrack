"""
Email-confirmation gate: keep unconfirmed users on the confirmation screen.

A freshly signed-up account (or one changing its email) must enter the
6-digit code before using anything else. This middleware redirects such
users to ``accounts:confirm_email`` (or the login page) while allowing the
confirmation surface itself, logout, and the Django admin to keep working.
"""

from django.shortcuts import redirect
from django.urls import resolve, reverse
from django.utils.deprecation import MiddlewareMixin


class RequireEmailConfirmationMiddleware(MiddlewareMixin):
    """Redirect authenticated-but-unconfirmed users to the code-entry page."""

    allowlist = {
        "accounts:confirm_email",
        "accounts:resend_confirmation_code",
        "accounts:logout",
    }

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = request.user
        if not (user.is_authenticated and not user.email_confirmed):
            return None
        if user.is_superuser:
            return None

        try:
            resolved = resolve(request.path)
        except Exception:
            return None

        if resolved.namespace and resolved.url_name:
            route = f"{resolved.namespace}:{resolved.url_name}"
            if route in self.allowlist:
                return None
        if request.path.startswith("/static/") or request.path.startswith("/media/"):
            return None
        if request.path.startswith("/admin/"):
            return None

        return redirect(reverse("accounts:confirm_email"))
