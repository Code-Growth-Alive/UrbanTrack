"""Signals: profile creation and security audit events for accounts."""

import hashlib

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.db.models.signals import post_save
from django.dispatch import receiver

from main.logging import audit


def _client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR")


def _fingerprint(value):
    """Stable, non-reversible identifier for security logs."""
    if not value:
        return None
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]


@receiver(post_save, sender="accounts.User")
def ensure_expert_profile(sender, instance, created, **kwargs):
    """
    Create the ExpertProfile for every account (all users are experts).

    Admins and superusers also get a profile so the public portfolio model
    applies uniformly to everyone.
    """
    from .models import ExpertProfile

    if not hasattr(instance, "expert_profile"):
        ExpertProfile.objects.get_or_create(user=instance)
    if created:
        audit("accounts.registered", user_id=instance.pk, role=instance.role)


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    audit("accounts.login", user_id=user.pk, ip=_client_ip(request))


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    audit(
        "accounts.logout",
        user_id=getattr(user, "pk", None),
        ip=_client_ip(request),
    )


@receiver(user_login_failed)
def log_login_failed(sender, credentials, request=None, **kwargs):
    audit(
        "accounts.login_failed",
        username_fingerprint=_fingerprint(credentials.get("username")),
        ip=_client_ip(request),
    )
