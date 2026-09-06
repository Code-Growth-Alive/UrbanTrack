"""
Cross-app orchestration for the publishing flow.

Publishing a project is the trigger of the whole cross-confirmation
workflow (business rule 1): it flips the project to ``published`` and asks
the certification app to dispatch invitations / notifications for every
declared contribution.
"""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from .models import ProjectStatus


class PublishingError(Exception):
    """Raised when a status transition is not allowed."""


def _ensure_owner_contribution(project):
    """
    The publishing user is automatically a contributor, and their
    contribution is confirmed outright: they lead the project they publish.
    """
    from django.utils import timezone

    from certification.models import ContributionStatus, ProjectContribution, RoleType

    project = ProjectContribution.objects.get_or_create(
        project=project,
        invited_email=project.published_by.email,
        role_type=RoleType.DIRECTOR,
        defaults={
            "expert": project.published_by,
            "added_by": project.published_by,
            "contribution_bullets": _("Led the delivery of the project from start to finish."),
            "status": ContributionStatus.CONFIRMED,
            "confirmed_at": timezone.now(),
        },
    )[0]
    return project


def publish_project(project):
    """
    Publish a draft project and dispatch expert invitations.

    Business rules enforced here:
      * only a ``draft`` project can be published (idempotency guard);
      * the project must be valid (dates, required fields);
      * every declared contribution without a registered expert receives an
        invitation (magic link); contributions linked to an existing account
        get the internal notification path instead (deduplication rule 5).
    """
    if project.status != ProjectStatus.DRAFT:
        raise PublishingError(f"Only a draft project can be published (current: {project.status}).")
    project.full_clean()
    project.status = ProjectStatus.PUBLISHED
    project.save(update_fields=["status", "updated_at"])

    # The publishing user is themselves a contributor, certified at publish time.
    _ensure_owner_contribution(project)

    from certification.services import notify_contributions_for_project

    notify_contributions_for_project(project)
    return project


def archive_project(project):
    """Archive a project; archived projects leave the public site."""
    if project.status != ProjectStatus.PUBLISHED:
        raise PublishingError(
            f"Only a published project can be archived (current: {project.status})."
        )
    project.status = ProjectStatus.ARCHIVED
    try:
        project.full_clean()
    except ValidationError:
        project.refresh_from_db()
        raise
    project.save(update_fields=["status", "updated_at"])
    return project
