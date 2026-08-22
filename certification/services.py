"""
Certification workflow state machine — the core business logic of Urban Track.

Every transition of ``ProjectContribution`` goes through this module so the
certification rules stay in one auditable place:

1. The company publishes a project and declares contributors
   (:func:`declare_contributor`, :func:`notify_contributions_for_project`).
2. Experts are invited: internal notification + email when the account
   exists, magic-link ``ExpertInvitation`` otherwise.
3. An experience becomes certified ONLY when the named expert personally
   validates it (:func:`confirm_as_is`) — never one-sided.
4. Adjusting the wording re-triggers validation: the contribution returns to
   ``pending_confirmation`` flagged for company re-validation
   (:func:`adjust_contribution` -> :func:`approve_adjustment`).
5. Emails matching an existing account are auto-linked, never duplicated.
6. Reminders are capped (:settings:`INVITATION_MAX_REMINDERS`) and stale
   invitations expire (:func:`expire_stale_invitations`).
7. Disputes go to admin arbitration (:func:`resolve_dispute`) — the only
   human intervention allowed in the certification flow.
8. Certified data cannot be silently modified: protected-field edits must
   start a new validation cycle (enforced here and in the model save()).
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import (
    ContributionStatus,
    ExpertInvitation,
    InvitationStatus,
    ProjectContribution,
    RoleType,
)


class CertificationError(Exception):
    """Base class for workflow errors surfaced to users."""


class PermissionDeniedError(CertificationError):
    """The actor is not allowed to perform this transition."""


class InvalidTransitionError(CertificationError):
    """The requested status transition is not allowed from the current state."""


def _actor_email(actor):
    return getattr(actor, "email", "") or ""


def _ensure_linked(contribution, actor):
    """
    Return the linked expert user for ``actor``, auto-linking when possible.

    Rule 5: an actor whose account email matches ``invited_email`` IS the
    declared expert — the contribution links to that account instead of any
    duplicate. Anonymous or mismatched actors are refused.
    """
    if getattr(actor, "is_authenticated", False) is False:
        raise PermissionDeniedError(_("Authentication required."))

    from django.contrib.auth import get_user_model

    User = get_user_model()

    if contribution.expert_id:
        if contribution.expert_id != actor.pk:
            raise PermissionDeniedError(
                _("Only the named expert can act on this contribution.")
            )
        return actor

    if _actor_email(actor).lower() != contribution.invited_email.lower():
        raise PermissionDeniedError(
            _("Only the named expert can act on this contribution.")
        )

    contribution.expert = User.objects.get(pk=actor.pk)
    contribution.invited_email = actor.email
    contribution.save(update_fields=["expert", "invited_email", "updated_at"])
    return contribution.expert


def _assert_company(contribution, actor):
    if not getattr(actor, "is_authenticated", False):
        raise PermissionDeniedError(_("Authentication required."))
    if contribution.added_by_id != actor.pk and not actor.is_superuser:
        raise PermissionDeniedError(
            _("Only the publishing company can validate this wording.")
        )


def declare_contributor(project, *, email, role_type, contribution_bullets, added_by):
    """
    Declare an expert contributor on a project (business rule 1).

    Auto-links to an existing expert account when the email already exists
    (rule 5); otherwise the contribution stays expert-less until the invited
    expert claims it through the magic-link landing (Epic 3).
    """
    if role_type not in RoleType.values:
        raise InvalidTransitionError(f"Unknown role type: {role_type}")

    from django.contrib.auth import get_user_model

    User = get_user_model()
    email = email.strip().lower()

    existing = User.objects.filter(email__iexact=email).first()
    if existing:
        if existing.role != "expert":
            raise ValidationError(
                _("This email belongs to a %(role)s account, not an individual expert.")
                % {"role": existing.get_role_display()}
            )
        if existing.pk == added_by.pk:
            raise ValidationError(
                _("The publishing company cannot declare itself as contributor.")
            )

    contribution = ProjectContribution(
        project=project,
        expert=existing,
        invited_email=email,
        role_type=role_type,
        contribution_bullets=contribution_bullets.strip(),
        added_by=added_by,
    )
    contribution.full_clean(exclude=["project"])
    contribution.save()
    return contribution


def _invitation_body(invitation):
    c = invitation.contribution
    return (
        f"You have been identified as a contributor to project "
        f"'{c.project.official_name}' by "
        f"{c.added_by.organisation_name or c.added_by.get_full_name()}.\n\n"
        f"Proposed role: {c.get_role_type_display()}.\n"
        f"Review and confirm your contribution before "
        f"{invitation.expires_at:%Y-%m-%d}:\n"
        f"{invitation.magic_link_path}\n\n"
        f"— Urban Track, the trust layer of urban development."
    )


def create_and_send_invitation(contribution):
    """Create the magic-link invitation and send the invitation email."""
    invitation = ExpertInvitation(contribution=contribution, email=contribution.invited_email)
    invitation.save()
    send_mail(
        subject=(
            f"[Urban Track] You have been identified as a contributor to "
            f"'{contribution.project.official_name}'"
        ),
        message=_invitation_body(invitation),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
    )
    return invitation


def _notify_registered_expert(contribution):
    """Email path for experts who already have an account (rule 2)."""
    send_mail(
        subject=(
            f"[Urban Track] Confirm your contribution to "
            f"'{contribution.project.official_name}'"
        ),
        message=(
            f"Hello {contribution.expert.get_full_name() or contribution.expert.username},\n\n"
            f"{contribution.added_by.organisation_name or 'A company'} identified you as "
            f"{contribution.get_role_type_display()} on project "
            f"'{contribution.project.official_name}'.\n"
            f"Log in to Urban Track to confirm, adjust or reject this contribution.\n\n"
            f"— Urban Track"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[contribution.invited_email],
    )
    if contribution.status == ContributionStatus.INVITED:
        contribution.status = ContributionStatus.PENDING_CONFIRMATION
        contribution.save(update_fields=["status", "updated_at"])


@transaction.atomic
def notify_contributions_for_project(project):
    """
    Dispatch invitations/notifications for every contribution of a project.

    Called by ``projects.services.publish_project`` (business rule 1 -> 2).
    Idempotent per contribution: registered experts get the internal path,
    unknown emails get exactly one active invitation each.
    """
    dispatched = {"invitations": [], "notified": []}
    for contribution in project.contributions.select_related("expert"):
        if contribution.status == ContributionStatus.REJECTED:
            continue
        if contribution.expert_id:
            _notify_registered_expert(contribution)
            dispatched["notified"].append(contribution)
            continue
        has_active = any(inv.is_active for inv in contribution.invitations.all())
        if not has_active:
            dispatched["invitations"].append(create_and_send_invitation(contribution))
    return dispatched


def get_by_token(token):
    """Return the active invitation for a magic-link token, or None."""
    invitation = (
        ExpertInvitation.objects.select_related(
            "contribution", "contribution__project", "contribution__added_by"
        )
        .filter(token=token)
        .first()
    )
    if invitation is None or not invitation.is_active:
        return None
    return invitation


def mark_invitation_opened(invitation):
    """
    Track an open/click on the invitation email (Epic 6 webhooks reuse this).

    First open moves the contribution from ``invited`` to
    ``pending_confirmation`` ("the expert saw it").
    """
    changed = False
    if invitation.status == InvitationStatus.SENT:
        invitation.status = InvitationStatus.OPENED
        changed = True
    contribution = invitation.contribution
    if contribution.status == ContributionStatus.INVITED:
        contribution.status = ContributionStatus.PENDING_CONFIRMATION
        contribution.save(update_fields=["status", "updated_at"])
    if changed:
        invitation.save(update_fields=["status"])
    return invitation


def send_invitation_reminder(invitation):
    """Send a reminder, capped at settings.INVITATION_MAX_REMINDERS (rule 6)."""
    if invitation.reminder_count >= settings.INVITATION_MAX_REMINDERS:
        raise InvalidTransitionError(_("Reminder budget exhausted."))
    if not invitation.is_active:
        raise InvalidTransitionError(_("This invitation is no longer active."))
    send_mail(
        subject=(
            f"[Urban Track] Reminder: confirm your contribution to "
            f"'{invitation.contribution.project.official_name}'"
        ),
        message=_invitation_body(invitation),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
    )
    invitation.reminder_count += 1
    invitation.save(update_fields=["reminder_count"])
    return invitation


def expire_stale_invitations(now=None):
    """Mark every overdue non-expired invitation as ``expired`` (rule 6)."""
    now = now or timezone.now()
    stale = ExpertInvitation.objects.filter(
        expires_at__lt=now
    ).exclude(status=InvitationStatus.EXPIRED)
    return stale.update(status=InvitationStatus.EXPIRED)


def confirm_as_is(contribution, actor):
    """Rule 3: the expert personally confirms what was declared -> certified."""
    expert = _ensure_linked(contribution, actor)
    if contribution.status not in ContributionStatus.actionable():
        raise InvalidTransitionError(
            f"Cannot confirm from status '{contribution.status}'."
        )
    contribution.pending_company_validation = False
    contribution.status = ContributionStatus.CONFIRMED
    contribution.confirmed_at = timezone.now()
    contribution.save()
    _notify_company_of_certification(contribution, expert)
    return contribution


def adjust_contribution(contribution, actor, *, contribution_bullets, role_type=None):
    """
    Rule 4: expert adjusts the proposed wording -> new validation cycle.

    The updated wording is stored and the contribution goes back to
    ``pending_confirmation`` awaiting COMPANY re-validation
    (:func:`approve_adjustment`), preserving independent double confirmation.
    """
    _ensure_linked(contribution, actor)
    if contribution.status in ContributionStatus.terminal() or (
        contribution.status == ContributionStatus.DISPUTED
    ):
        raise InvalidTransitionError(
            f"Cannot adjust from status '{contribution.status}'."
        )
    old_status = contribution.status
    contribution.contribution_bullets = contribution_bullets.strip()
    if role_type:
        if role_type not in RoleType.values:
            raise InvalidTransitionError(f"Unknown role type: {role_type}")
        contribution.role_type = role_type
    contribution.pending_company_validation = True
    contribution.status = ContributionStatus.PENDING_CONFIRMATION
    contribution.save()
    if old_status == ContributionStatus.CONFIRMED:
        contribution.confirmed_at = None
        contribution.save(update_fields=["confirmed_at"])
    _request_company_revalidation(contribution, actor)
    return contribution


def approve_adjustment(contribution, actor):
    """
    Company side of the adjustment cycle (rule 4): validate the adjusted
    wording. Refused unless an expert adjustment is actually pending, so the
    company can never certify unilaterally (rule 3).
    """
    _assert_company(contribution, actor)
    if not contribution.pending_company_validation:
        raise InvalidTransitionError(
            _("No expert-adjusted wording awaits validation.")
        )
    if contribution.status != ContributionStatus.PENDING_CONFIRMATION:
        raise InvalidTransitionError(
            f"Cannot approve from status '{contribution.status}'."
        )
    contribution.pending_company_validation = False
    contribution.status = ContributionStatus.CONFIRMED
    contribution.confirmed_at = timezone.now()
    contribution.save()
    return contribution


def reject_contribution(contribution, actor, reason=""):
    """Expert refuses the declared contribution (terminal state)."""
    _ensure_linked(contribution, actor)
    if contribution.status not in ContributionStatus.actionable():
        raise InvalidTransitionError(
            f"Cannot reject from status '{contribution.status}'."
        )
    contribution.rejection_reason = reason.strip()
    contribution.status = ContributionStatus.REJECTED
    contribution.save()
    return contribution


def dispute_contribution(contribution, actor, reason=""):
    """
    Expert contests the declaration -> ``disputed`` (rule 7).

    Disputed contributions land in the admin arbitration queue; only an
    administrator can move them forward (:func:`resolve_dispute`).
    """
    _ensure_linked(contribution, actor)
    if not reason.strip():
        raise ValidationError({"dispute_reason": _("A dispute reason is required.")})
    if contribution.status in ContributionStatus.terminal():
        raise InvalidTransitionError(
            f"Cannot dispute from status '{contribution.status}'."
        )
    contribution.dispute_reason = reason.strip()
    contribution.status = ContributionStatus.DISPUTED
    contribution.save()
    return contribution


def resolve_dispute(contribution, staff_user, *, outcome, note=""):
    """
    Admin arbitration (rule 7) — the ONLY human intervention in the flow.

    Outcomes: ``confirm`` (certify as declared), ``reject`` (side with the
    expert), ``return_to_expert`` (send back for a fresh confirmation cycle).
    """
    if not getattr(staff_user, "is_staff", False):
        raise PermissionDeniedError(_("Only administrators can arbitrate disputes."))
    if contribution.status != ContributionStatus.DISPUTED:
        raise InvalidTransitionError("Only disputed contributions can be arbitrated.")

    if outcome == "confirm":
        contribution.status = ContributionStatus.CONFIRMED
        contribution.confirmed_at = timezone.now()
        update_fields = ["status", "confirmed_at"]
    elif outcome == "reject":
        contribution.status = ContributionStatus.REJECTED
        update_fields = ["status"]
    elif outcome == "return_to_expert":
        contribution.status = ContributionStatus.PENDING_CONFIRMATION
        update_fields = ["status"]
    else:
        raise InvalidTransitionError(f"Unknown arbitration outcome: {outcome}")
    contribution.dispute_reason = (
        f"{contribution.dispute_reason}\n[arbitration] {note}".strip()
        if note
        else contribution.dispute_reason
    )
    contribution.save(update_fields=[*update_fields, "dispute_reason", "updated_at"])
    return contribution


def _notify_company_of_certification(contribution, expert):
    send_mail(
        subject=(
            f"[Urban Track] {expert.get_full_name() or expert.email} confirmed "
            f"their contribution to '{contribution.project.official_name}'"
        ),
        message=(
            "The experience is now certified via cross-confirmation and "
            "appears on the expert's public profile.\n\n— Urban Track"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[contribution.added_by.email],
    )


def _request_company_revalidation(contribution, expert_actor):
    send_mail(
        subject=(
            f"[Urban Track] Action needed: {expert_actor.get_full_name()} adjusted "
            f"their contribution to '{contribution.project.official_name}'"
        ),
        message=(
            f"The expert adjusted the wording:\n\n"
            f"{contribution.contribution_bullets}\n\n"
            f"Validate the adjusted wording in your company dashboard.\n\n— Urban Track"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[contribution.added_by.email],
    )
