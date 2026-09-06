"""Signals: every user owns a public portfolio profile."""

from django.db.models.signals import post_save
from django.dispatch import receiver


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
