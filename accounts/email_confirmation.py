"""
Email confirmation: 6-digit code, 24h validity, auto-deletion of accounts.

A freshly signed-up user (or one who changes their email) receives a code by
email. They must enter it before the code expires. If an account is still
unconfirmed 24h after the code was issued, it is deleted by the scheduled
command ``accounts.management.commands.purge_unconfirmed``.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from main.emails import send_branded_mail


class ConfirmationError(Exception):
    """Base error for email-confirmation operations."""


def generate_code():
    """Return a fresh 6-digit confirmation code (e.g. ``483920``)."""
    return "".join(secrets.choice("0123456789") for _ in range(settings.CONFIRMATION_CODE_LENGTH))


def _is_code_expired(user):
    created = user.confirmation_code_created_at
    if created is None:
        return True
    return timezone.now() > created + timedelta(hours=settings.CONFIRMATION_CODE_TTL_HOURS)


def issue_confirmation_code(user, *, send=True):
    """Generate, store and (by default) email a fresh 6-digit code."""
    user.confirmation_code = generate_code()
    user.confirmation_code_created_at = timezone.now()
    user.save(update_fields=["confirmation_code", "confirmation_code_created_at"])
    if send:
        send_confirmation_code(user)
    return user.confirmation_code


def send_confirmation_code(user):
    """Send the stored code to the user's email."""
    code = user.confirmation_code
    if not code:
        raise ConfirmationError(_("No confirmation code has been issued for this account."))
    name = user.get_full_name() or user.username
    send_branded_mail(
        subject=_("[Urban Track] Confirm your email address"),
        text=_(
            "Hello %(name)s,\n\n"
            "Your Urban Track confirmation code is: %(code)s\n"
            "Enter it on the confirmation page to activate your account.\n"
            "The code expires in 24 hours.\n\n"
            "— Urban Track"
        )
        % {"name": name, "code": code},
        recipient_list=[user.email],
        template="emails/confirmation_code.html",
        context={
            "heading": "Confirm your email address",
            "preheader": "Your 6-digit Urban Track confirmation code.",
            "name": name,
            "code": code,
            "expires_in": settings.CONFIRMATION_CODE_TTL_HOURS,
            "confirm_url": _confirm_url(),
        },
    )


def _confirm_url():
    from django.urls import reverse

    from main.emails import absolute_url

    return absolute_url(reverse("accounts:confirm_email"))


def confirm_email(user, code):
    """Validate ``code`` against the user's stored code; confirm on success."""
    if not code:
        raise ConfirmationError(_("Please enter the 6-digit confirmation code."))
    if user.confirmation_code != code.strip():
        raise ConfirmationError(_("That confirmation code is incorrect."))
    if _is_code_expired(user):
        raise ConfirmationError(_("This confirmation code has expired. Request a new one."))
    user.email_confirmed = True
    user.confirmation_code = ""
    user.confirmation_code_created_at = None
    user.save(
        update_fields=["email_confirmed", "confirmation_code", "confirmation_code_created_at"]
    )
    return user


def is_confirmation_expired(user):
    """True when the issued code (and thus the unconfirmed state) has expired."""
    return _is_code_expired(user)


def purge_expired_unconfirmed(hours=None):
    """
    Delete accounts that are still unconfirmed after the 24h window.

    Returns the number of deleted accounts. Only touches accounts created
    with a confirmation code whose window has elapsed.
    """
    hours = hours or settings.CONFIRMATION_CODE_TTL_HOURS
    from django.db.models import Q

    User = get_user_model()
    cutoff = timezone.now() - timedelta(hours=hours)
    qs = User.objects.filter(
        email_confirmed=False,
        confirmation_code_created_at__lt=cutoff,
    ).filter(Q(confirmation_code_created_at__isnull=False) & ~Q(is_superuser=True))
    count = qs.count()
    qs.delete()
    return count
