"""Signals: keep expert portfolios in sync with account roles."""

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save)
def ensure_expert_profile(sender, instance, **kwargs):
    """
    Create the ExpertProfile whenever a user becomes an individual expert.

    Runs on creation and on role change; companies and donor agencies never
    get a portfolio.
    """
    from .models import ExpertProfile, Role

    if sender.__name__ != "User" or not hasattr(instance, "role"):
        return
    if instance.role == Role.EXPERT:
        ExpertProfile.objects.get_or_create(user=instance)
