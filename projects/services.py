"""
Cross-app orchestration for the publishing flow.

Publishing a project is the trigger of the whole cross-confirmation
workflow (business rule 1): it flips the project to ``published`` and asks
the certification app to dispatch invitations / notifications for every
declared contribution.
"""

from django.core.exceptions import ValidationError

from .models import ProjectStatus


class PublishingError(Exception):
    """Raised when a status transition is not allowed."""


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
