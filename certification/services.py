"""
Certification workflow state machine: the core business logic of Urban Track.

Every transition of ``ProjectContribution`` goes through this module so the
certification rules stay in one auditable place:

1. The company publishes a project and declares contributors
   (:func:`declare_contributor`, :func:`notify_contributions_for_project`).
2. Experts are invited: internal notification + email when the account
   exists, magic-link ``ExpertInvitation`` otherwise.
3. An experience becomes certified ONLY when the named expert personally
   validates it (:func:`confirm_as_is`): never one-sided.
4. Adjusting the wording re-triggers validation: the contribution returns to
   ``pending_confirmation`` flagged for company re-validation
   (:func:`adjust_contribution` -> :func:`approve_adjustment`).
5. Emails matching an existing account are auto-linked, never duplicated.
6. Reminders are capped (:settings:`INVITATION_MAX_REMINDERS`) and stale
   invitations expire (:func:`expire_stale_invitations`).
7. Disputes go to admin arbitration (:func:`resolve_dispute`): the only
   human intervention allowed in the certification flow.
8. Certified data cannot be silently modified: protected-field edits must
   start a new validation cycle (enforced here and in the model save()).
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from main.emails import absolute_url, send_branded_mail

from .models import (
    ConfirmationSource,
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
    declared expert: the contribution links to that account instead of any
    duplicate. Anonymous or mismatched actors are refused.
    """
    if getattr(actor, "is_authenticated", False) is False:
        raise PermissionDeniedError(_("Authentification requise."))

    from django.contrib.auth import get_user_model

    User = get_user_model()

    if contribution.expert_id:
        if contribution.expert_id != actor.pk:
            raise PermissionDeniedError(_("Seul l'expert nommé peut agir sur cette contribution."))
        return actor

    if _actor_email(actor).lower() != contribution.invited_email.lower():
        raise PermissionDeniedError(_("Seul l'expert nommé peut agir sur cette contribution."))

    contribution.expert = User.objects.get(pk=actor.pk)
    contribution.invited_email = actor.email
    contribution.save(update_fields=["expert", "invited_email", "updated_at"])
    return contribution.expert


def _assert_company(contribution, actor):
    if not getattr(actor, "is_authenticated", False):
        raise PermissionDeniedError(_("Authentification requise."))
    if contribution.added_by_id != actor.pk and not actor.is_superuser:
        raise PermissionDeniedError(
            _("Seule la structure qui a publié le projet peut valider cette formulation.")
        )


def declare_contributor(
    project,
    *,
    email,
    role_type,
    contribution_bullets,
    added_by,
    confirmation_source=ConfirmationSource.EXPERT,
):
    """
    Declare an expert contributor on a project (business rule 1).

    Auto-links to an existing expert account when the email already exists
    (rule 5); otherwise the contribution stays expert-less until the invited
    expert claims it through the magic-link landing (Epic 3).

    T1 rule: a physical person cannot be both the declarant and the
    confirmer of their own contribution. The project publisher is the
    legitimate exception (the company attests its director's role at publish
    time); anyone else trying to declare *themselves* on a project they do
    not publish is refused here — and a refused declaration is never
    persisted, so it can never surface as "certified".
    """
    if role_type not in RoleType.values:
        raise InvalidTransitionError(f"Type de rôle inconnu : {role_type}")

    if confirmation_source not in ConfirmationSource.values:
        raise InvalidTransitionError(f"Source de confirmation inconnue : {confirmation_source}")

    from django.contrib.auth import get_user_model

    User = get_user_model()
    email = email.strip().lower()

    existing = User.objects.filter(email__iexact=email).first()
    if existing:
        owner = project.published_by
        self_declared = existing.pk == added_by.pk
        if self_declared and owner is not None and owner.pk != added_by.pk:
            raise ValidationError(
                _(
                    "Vous ne pouvez pas vous déclarer vous-même comme "
                    "contributeur : une personne physique ne peut pas être à la "
                    "fois le déclarant et le confirmateur de la même "
                    "contribution. Demandez à la structure qui publie le projet de vous "
                    "déclarer à la place."
                )
            )

    contribution = ProjectContribution(
        project=project,
        expert=existing,
        invited_email=email,
        role_type=role_type,
        contribution_bullets=contribution_bullets.strip(),
        added_by=added_by,
        confirmation_source=confirmation_source,
    )
    contribution.full_clean(exclude=["project"])
    contribution.save()
    return contribution


def _invitation_body(invitation):
    c = invitation.contribution
    return (
        f"Vous avez été identifié comme contributeur au projet "
        f"'{c.project.official_name}' par "
        f"{c.added_by.organisation_name or c.added_by.get_full_name()}.\n\n"
        f"Rôle proposé : {c.get_role_type_display()}.\n"
        f"Examinez et confirmez votre contribution avant le "
        f"{invitation.expires_at:%Y-%m-%d}:\n"
        f"{absolute_url(invitation.magic_link_path)}\n\n"
        f"— Urban Track, la couche de confiance du développement urbain."
    )


def create_and_send_invitation(contribution):
    """Create the magic-link invitation and send the invitation email."""
    invitation = ExpertInvitation(contribution=contribution, email=contribution.invited_email)
    invitation.save()
    confirm_url = absolute_url(invitation.magic_link_path)
    send_branded_mail(
        subject=(
            f"[Urban Track] Vous avez été identifié comme contributeur au projet "
            f"'{contribution.project.official_name}'"
        ),
        text=_invitation_body(invitation),
        recipient_list=[invitation.email],
        template="emails/invitation.html",
        context={
            "heading": "Vous avez été identifié comme contributeur",
            "preheader": (
                "Un expert du projet "
                f"'{contribution.project.official_name}' : confirmez avant le "
                f"{invitation.expires_at:%Y-%m-%d}."
            ),
            "contribution": contribution,
            "invitation": invitation,
            "company": (
                contribution.added_by.organisation_name or contribution.added_by.get_full_name()
            ),
            "confirm_url": confirm_url,
        },
    )
    return invitation


def _notify_registered_expert(contribution):
    """Email path for experts who already have an account (rule 2)."""
    name = contribution.expert.get_full_name() or contribution.expert.username
    send_branded_mail(
        subject=(
            f"[Urban Track] Confirmez votre contribution au projet "
            f"'{contribution.project.official_name}'"
        ),
        text=(
            f"Bonjour {name},\n\n"
            f"{contribution.added_by.organisation_name or 'Une structure'} vous a identifié "
            f"comme {contribution.get_role_type_display()} sur le projet "
            f"'{contribution.project.official_name}'.\n"
            f"Ouvrez votre tableau de bord Urban Track pour confirmer, ajuster ou "
            f"refuser cette contribution.\n\n"
            f"— Urban Track"
        ),
        recipient_list=[contribution.invited_email],
        template="emails/expert_notification.html",
        context={
            "heading": "Confirmez votre contribution",
            "preheader": (
                f"{contribution.added_by.organisation_name or 'Une structure'} vous a identifié "
                f"sur '{contribution.project.official_name}'."
            ),
            "contribution": contribution,
            "company": (contribution.added_by.organisation_name or "Une structure"),
            "name": name,
            "dashboard_url": absolute_url("/accounts/dashboard/"),
        },
    )
    if contribution.status == ContributionStatus.INVITED:
        contribution.status = ContributionStatus.PENDING_CONFIRMATION
        contribution.save(update_fields=["status", "updated_at"])


def notify_contribution(contribution):
    """
    Dispatch the right channel for ONE contribution (Epic 2 late additions).

    Registered expert -> internal email + status bump; unknown email ->
    exactly one active magic-link invitation. Idempotent and safe to call
    repeatedly. Returns ``(kind, payload)`` where kind is ``"notified"`` /
    ``"invited"`` / ``None`` and payload mirrors the original dispatcher
    contract (the contribution, resp. the created invitation).
    """
    if contribution.status == ContributionStatus.REJECTED:
        return None, None
    if contribution.expert_id:
        _notify_registered_expert(contribution)
        return "notified", contribution
    if any(inv.is_active for inv in contribution.invitations.all()):
        return None, None
    invitation = create_and_send_invitation(contribution)
    return "invited", invitation


@transaction.atomic
def notify_contributions_for_project(project):
    """
    Dispatch invitations/notifications for every contribution of a project.

    Called by ``projects.services.publish_project`` (business rule 1 -> 2).
    Idempotent per contribution: registered experts get the internal path,
    unknown emails get exactly one active invitation each.
    """
    dispatched = {"invitations": [], "notified": []}
    buckets = {"invited": "invitations", "notified": "notified"}
    for contribution in project.contributions.select_related("expert"):
        # The publisher's own contribution is auto-confirmed at publish time:
        # there is nothing to invite or ask them to confirm.
        if contribution.expert_id and contribution.expert_id == contribution.added_by_id:
            continue
        kind, payload = notify_contribution(contribution)
        if kind is not None:
            dispatched[buckets[kind]].append(payload)
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
        raise InvalidTransitionError(_("Budget de relance épuisé."))
    if not invitation.is_active:
        raise InvalidTransitionError(_("Cette invitation n'est plus active."))
    contribution = invitation.contribution
    confirm_url = absolute_url(invitation.magic_link_path)
    send_branded_mail(
        subject=(
            f"[Urban Track] Rappel : confirmez votre contribution au projet "
            f"'{contribution.project.official_name}'"
        ),
        text=_invitation_body(invitation),
        recipient_list=[invitation.email],
        template="emails/reminder.html",
        context={
            "heading": "Un petit rappel",
            "preheader": (
                f"Confirmez votre contribution au projet '{contribution.project.official_name}' "
                f"avant le {invitation.expires_at:%Y-%m-%d}."
            ),
            "contribution": contribution,
            "invitation": invitation,
            "company": (
                contribution.added_by.organisation_name or contribution.added_by.get_full_name()
            ),
            "confirm_url": confirm_url,
        },
    )
    invitation.reminder_count += 1
    invitation.save(update_fields=["reminder_count"])
    return invitation


def expire_stale_invitations(now=None):
    """Mark every overdue non-expired invitation as ``expired`` (rule 6)."""
    now = now or timezone.now()
    stale = ExpertInvitation.objects.filter(expires_at__lt=now).exclude(
        status=InvitationStatus.EXPIRED
    )
    return stale.update(status=InvitationStatus.EXPIRED)


def confirm_as_is(contribution, actor):
    """Rule 3: the expert personally confirms what was declared -> certified."""
    expert = _ensure_linked(contribution, actor)
    if contribution.status not in ContributionStatus.actionable():
        raise InvalidTransitionError(
            f"Impossible de confirmer à partir du statut '{contribution.status}'."
        )
    contribution.pending_company_validation = False
    contribution.status = ContributionStatus.CONFIRMED
    contribution.confirmed_at = timezone.now()
    contribution.confirmed_by = ConfirmationSource.EXPERT
    contribution.save()
    _notify_company_of_certification(contribution, expert)
    return contribution


def request_client_confirmation(contribution, actor, *, client_email):
    """
    T1 path 1: a sole trader / small consultancy publishes; the client
    (maître d'ouvrage) counter-signs the role instead of the expert.

    Only the publishing user (or their company) can request this. An email
    with a secure one-time link is sent to the client; the link holder can
    confirm without an account. Returns the confirmation token.
    """
    _assert_company(contribution, actor)
    if contribution.status in ContributionStatus.terminal():
        raise InvalidTransitionError(
            f"Impossible de demander une confirmation à partir du statut '{contribution.status}'."
        )
    if contribution.confirmation_source != ConfirmationSource.CLIENT:
        raise InvalidTransitionError(
            _("Cette contribution n'est pas configurée pour une confirmation par le client.")
        )

    token = uuid.uuid4()
    contribution.client_confirm_token = token
    contribution.save(update_fields=["client_confirm_token", "updated_at"])

    from main.emails import absolute_url, send_branded_mail

    confirm_path = f"/certification/client-confirm/{token}/"
    send_branded_mail(
        subject=(
            f"[Urban Track] Confirmez la contribution de "
            f"{contribution.expert or contribution.invited_email} au projet "
            f"'{contribution.project.official_name}'"
        ),
        text=(
            f"Bonjour,\n\n"
            f"{contribution.added_by.organisation_name or contribution.added_by.get_full_name()} "
            f"a publié le projet '{contribution.project.official_name}' et vous demande, "
            f"en tant que client / maître d'ouvrage, de confirmer le rôle de "
            f"{contribution.expert or contribution.invited_email} "
            f"({contribution.get_role_type_display()}).\n\n"
            f"Confirmez en tant que client / maître d'ouvrage en ouvrant ce lien à "
            f"usage unique avant qu'il ne soit révoqué :\n"
            f"{absolute_url(confirm_path)}\n\n"
            f"— Urban Track, la couche de confiance du développement urbain."
        ),
        recipient_list=[client_email],
        template="emails/client_confirmation.html",
        context={
            "heading": "Confirmer la contribution d'un expert",
            "preheader": (
                f"Confirmez la contribution au projet '{contribution.project.official_name}' "
                "en tant que client / maître d'ouvrage."
            ),
            "contribution": contribution,
            "client_email": client_email,
            "confirm_url": absolute_url(confirm_path),
        },
    )
    return contribution.client_confirm_token


def confirm_by_client(contribution, token):
    """
    T1 path 1 (client side): certify a contribution via the one-time token.

    Unauthenticated by design: the client has no Urban Track account. The
    token is single-use and cannot be replayed after a successful
    confirmation or a rejection.
    """
    if contribution.client_confirm_token != token:
        raise PermissionDeniedError(
            _("Ce lien de confirmation est invalide ou a déjà été utilisé.")
        )
    if contribution.status not in ContributionStatus.actionable():
        raise InvalidTransitionError(
            f"Impossible de confirmer à partir du statut '{contribution.status}'."
        )
    contribution.client_confirm_token = None
    contribution.pending_company_validation = False
    contribution.status = ContributionStatus.CONFIRMED
    contribution.confirmed_at = timezone.now()
    contribution.confirmed_by = ConfirmationSource.CLIENT
    contribution.save()
    return contribution


def claim_client_contribution_token(token):
    """Return the contribution behind a client-confirmation link, or None."""
    contribution = ProjectContribution.objects.filter(client_confirm_token=token).first()
    if contribution is None or contribution.status not in ContributionStatus.actionable():
        return None
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
            f"Impossible d'ajuster à partir du statut '{contribution.status}'."
        )
    old_status = contribution.status
    contribution.contribution_bullets = contribution_bullets.strip()
    if role_type:
        if role_type not in RoleType.values:
            raise InvalidTransitionError(f"Type de rôle inconnu : {role_type}")
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
            _("Aucune formulation ajustée par l'expert n'attend de validation.")
        )
    if contribution.status != ContributionStatus.PENDING_CONFIRMATION:
        raise InvalidTransitionError(
            f"Impossible d'approuver à partir du statut '{contribution.status}'."
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
            f"Impossible de refuser à partir du statut '{contribution.status}'."
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
        raise ValidationError({"dispute_reason": _("Un motif de contestation est requis.")})
    if contribution.status in ContributionStatus.terminal():
        raise InvalidTransitionError(
            f"Impossible de contester à partir du statut '{contribution.status}'."
        )
    contribution.dispute_reason = reason.strip()
    contribution.status = ContributionStatus.DISPUTED
    contribution.save()
    return contribution


def resolve_dispute(contribution, staff_user, *, outcome, note=""):
    """
    Admin arbitration (rule 7): the ONLY human intervention in the flow.

    Outcomes: ``confirm`` (certify as declared), ``reject`` (side with the
    expert), ``return_to_expert`` (send back for a fresh confirmation cycle).
    """
    if not getattr(staff_user, "is_staff", False):
        raise PermissionDeniedError(
            _("Seuls les administrateurs peuvent arbitrer les contestations.")
        )
    if contribution.status != ContributionStatus.DISPUTED:
        raise InvalidTransitionError("Seules les contributions contestées peuvent être arbitrées.")

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
        raise InvalidTransitionError(f"Issue d'arbitrage inconnue : {outcome}")
    contribution.dispute_reason = (
        f"{contribution.dispute_reason}\n[arbitrage] {note}".strip()
        if note
        else contribution.dispute_reason
    )
    contribution.save(update_fields=[*update_fields, "dispute_reason", "updated_at"])
    return contribution


def _notify_company_of_certification(contribution, expert):
    name = expert.get_full_name() or expert.email
    send_branded_mail(
        subject=(
            f"[Urban Track] {name} a confirmé "
            f"sa contribution au projet '{contribution.project.official_name}'"
        ),
        text=(
            "L'expérience est désormais certifiée via la double confirmation et "
            "apparaît sur le profil public de l'expert.\n\n— Urban Track"
        ),
        recipient_list=[contribution.added_by.email],
        template="emails/company_confirmation.html",
        context={
            "heading": "Contribution certifiée",
            "preheader": (
                f"{name} a confirmé sa contribution au projet "
                f"'{contribution.project.official_name}'."
            ),
            "contribution": contribution,
            "name": name,
            "expert_email": expert.email,
            "dashboard_url": absolute_url("/accounts/dashboard/"),
        },
    )


def _request_company_revalidation(contribution, expert_actor):
    name = expert_actor.get_full_name() or expert_actor.username
    send_branded_mail(
        subject=(
            f"[Urban Track] Action requise : {name} a ajusté "
            f"sa contribution au projet '{contribution.project.official_name}'"
        ),
        text=(
            f"L'expert a ajusté la formulation :\n\n"
            f"{contribution.contribution_bullets}\n\n"
            f"Validez la formulation ajustée depuis le tableau de bord de votre "
            f"structure.\n\n— Urban Track"
        ),
        recipient_list=[contribution.added_by.email],
        template="emails/company_revalidation.html",
        context={
            "heading": "Action requise : valider la formulation ajustée",
            "preheader": (
                f"{name} a ajusté sa contribution au projet "
                f"'{contribution.project.official_name}'."
            ),
            "contribution": contribution,
            "name": name,
            "validate_url": absolute_url("/accounts/dashboard/"),
        },
    )
