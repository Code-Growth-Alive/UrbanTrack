"""
Tests of the cross-confirmation state machine (certification.services).

These tests ARE the executable specification of the core business rules
(spec section 5). Every rule number below references that section.
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase

from projects.models import ProjectStatus
from projects.services import publish_project
from projects.tests.test_models import make_company, make_project

from ..models import (
    ConfirmationSource,
    ContributionStatus,
    ExpertInvitation,
    InvitationStatus,
    ProjectContribution,
    RoleType,
)
from ..services import (
    InvalidTransitionError,
    PermissionDeniedError,
    adjust_contribution,
    approve_adjustment,
    claim_client_contribution_token,
    confirm_as_is,
    confirm_by_client,
    declare_contributor,
    dispute_contribution,
    expire_stale_invitations,
    get_by_token,
    mark_invitation_opened,
    notify_contributions_for_project,
    reject_contribution,
    request_client_confirmation,
    resolve_dispute,
    send_invitation_reminder,
)
from .test_models import make_expert

User = get_user_model()


def linked_contribution(company, expert, **kwargs):
    return declare_contributor(
        make_project(company) if "project" not in kwargs else kwargs.pop("project"),
        email=expert.email,
        role_type=kwargs.pop("role_type", RoleType.SPECIALIST),
        contribution_bullets=kwargs.pop("contribution_bullets", "- Did the thing"),
        added_by=company,
        confirmation_source=kwargs.pop("confirmation_source", ConfirmationSource.EXPERT),
    )


class DeclareContributorTests(TestCase):
    """Rules 1 + 5: company declares; emails matching accounts auto-link.

    T1: a physical person cannot be both the declarant and the confirmer of
    their own contribution. The project publisher is the legitimate exception
    (sole trader / director case); a non-publisher cannot self-declare.
    """

    def setUp(self):
        self.company = make_company()

    def test_unknown_email_stays_expert_less(self):
        contribution = declare_contributor(
            make_project(self.company),
            email="stranger@example.com",
            role_type=RoleType.MANAGER,
            contribution_bullets="x",
            added_by=self.company,
        )
        self.assertIsNone(contribution.expert)
        self.assertEqual(contribution.status, ContributionStatus.INVITED)

    def test_known_email_auto_links_to_existing_account(self):
        expert = make_expert(email="known@example.com")
        contribution = declare_contributor(
            make_project(self.company),
            email="KNOWN@Example.com",
            role_type=RoleType.MANAGER,
            contribution_bullets="x",
            added_by=self.company,
        )
        self.assertEqual(contribution.expert_id, expert.id)
        self.assertEqual(contribution.invited_email, "known@example.com")

    def test_publisher_can_declare_themselves_sole_trader(self):
        """T1: the individual consultant (publisher = expert) is allowed."""
        project = make_project(self.company)  # published_by == self.company
        contribution = declare_contributor(
            project,
            email=self.company.email,
            role_type=RoleType.DIRECTOR,
            contribution_bullets="x",
            added_by=self.company,
        )
        self.assertEqual(contribution.expert_id, self.company.id)
        self.assertFalse(contribution.is_certified)

    def test_non_publisher_cannot_declare_themselves(self):
        """T1: declarant and confirmer must be distinct physical persons."""
        other = make_company(username="other", email="other@example.com")
        project = make_project(self.company)
        with self.assertRaises(ValidationError):
            declare_contributor(
                project,
                email=other.email,
                role_type=RoleType.DIRECTOR,
                contribution_bullets="x",
                added_by=other,
            )

    def test_refused_declaration_is_never_persisted(self):
        """T1: a refused declaration cannot produce a 'certified' badge."""
        other = make_company(username="other", email="other@example.com")
        project = make_project(self.company)
        before = ProjectContribution.objects.count()
        with self.assertRaises(ValidationError):
            declare_contributor(
                project,
                email=other.email,
                role_type=RoleType.DIRECTOR,
                contribution_bullets="x",
                added_by=other,
            )
        self.assertEqual(ProjectContribution.objects.count(), before)

    def test_confirmation_source_is_stored(self):
        contribution = declare_contributor(
            make_project(self.company),
            email="stranger@example.com",
            role_type=RoleType.SPECIALIST,
            contribution_bullets="x",
            added_by=self.company,
            confirmation_source=ConfirmationSource.CLIENT,
        )
        contribution.refresh_from_db()
        self.assertEqual(contribution.confirmation_source, ConfirmationSource.CLIENT)


class DispatchTests(TestCase):
    """Rule 2: registered experts are notified; unknown emails get invitations."""

    def setUp(self):
        self.company = make_company()

    def test_registered_expert_notified_without_invitation_row(self):
        expert = make_expert()
        contribution = linked_contribution(self.company, expert)
        mail.outbox.clear()
        dispatched = notify_contributions_for_project(contribution.project)
        self.assertEqual(len(dispatched["invitations"]), 0)
        self.assertEqual(len(mail.outbox), 1)
        contribution.refresh_from_db()
        self.assertEqual(contribution.status, ContributionStatus.PENDING_CONFIRMATION)

    def test_unknown_email_gets_single_magic_link_invitation(self):
        contribution = declare_contributor(
            make_project(self.company),
            email="ghost@example.com",
            role_type=RoleType.ASSISTANT,
            contribution_bullets="x",
            added_by=self.company,
        )
        mail.outbox.clear()
        dispatched = notify_contributions_for_project(contribution.project)
        self.assertEqual(len(dispatched["invitations"]), 1)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn("Vous avez été identifié comme contributeur", body)
        self.assertIn(dispatched["invitations"][0].magic_link_path, body)

    def test_dispatch_is_idempotent_per_contribution(self):
        contribution = declare_contributor(
            make_project(self.company),
            email="ghost@example.com",
            role_type=RoleType.ASSISTANT,
            contribution_bullets="x",
            added_by=self.company,
        )
        mail.outbox.clear()
        notify_contributions_for_project(contribution.project)
        first_count = ExpertInvitation.objects.count()
        notify_contributions_for_project(contribution.project)
        self.assertEqual(ExpertInvitation.objects.count(), first_count)

    def test_publish_triggers_dispatch(self):
        project = make_project(self.company)
        linked_contribution(self.company, make_expert(), project=project)
        declare_contributor(
            project,
            email="ghost@example.com",
            role_type=RoleType.ASSISTANT,
            contribution_bullets="x",
            added_by=self.company,
        )
        mail.outbox.clear()
        publish_project(project)
        self.assertEqual(project.status, ProjectStatus.PUBLISHED)
        self.assertEqual(ExpertInvitation.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)


class ConfirmRejectDisputeTests(TestCase):
    """Rule 3: only the expert's personal action certifies."""

    def setUp(self):
        self.company = make_company()
        self.project = make_project(self.company)
        self.expert = make_expert()

    def test_confirm_as_is_certifies_and_sets_confirmed_at(self):
        contribution = linked_contribution(self.company, self.expert, project=self.project)
        confirm_as_is(contribution, self.expert)
        contribution.refresh_from_db()
        self.assertTrue(contribution.is_certified)
        self.assertIsNotNone(contribution.confirmed_at)

    def test_only_named_expert_can_confirm(self):
        contribution = linked_contribution(self.company, self.expert, project=self.project)
        stranger = make_expert(username="stranger", email="s@example.com")
        with self.assertRaises(PermissionDeniedError):
            confirm_as_is(contribution, stranger)
        with self.assertRaises(PermissionDeniedError):
            confirm_as_is(contribution, self.company)

    def test_matching_email_auto_links_before_confirmation(self):
        """A contribution created outside the service layer links on first action."""
        contribution = ProjectContribution.objects.create(
            project=self.project,
            invited_email=self.expert.email.upper(),
            role_type=RoleType.MANAGER,
            contribution_bullets="x",
            added_by=self.company,
        )
        self.assertIsNone(contribution.expert)
        confirm_as_is(contribution, User.objects.get(pk=self.expert.pk))
        contribution.refresh_from_db()
        self.assertEqual(contribution.expert_id, self.expert.pk)
        self.assertTrue(contribution.is_certified)

    def test_double_confirmation_refused(self):
        contribution = linked_contribution(self.company, self.expert, project=self.project)
        confirm_as_is(contribution, self.expert)
        with self.assertRaises(InvalidTransitionError):
            confirm_as_is(contribution, self.expert)

    def test_rejected_is_terminal(self):
        contribution = linked_contribution(self.company, self.expert, project=self.project)
        reject_contribution(contribution, self.expert, reason="Was not on this project")
        self.assertEqual(contribution.status, ContributionStatus.REJECTED)
        with self.assertRaises(InvalidTransitionError):
            confirm_as_is(contribution, self.expert)

    def test_dispute_requires_reason_and_freezes_flow(self):
        contribution = linked_contribution(self.company, self.expert, project=self.project)
        with self.assertRaises(ValidationError):
            dispute_contribution(contribution, self.expert, reason="")
        dispute_contribution(contribution, self.expert, reason="Wrong dates")
        self.assertEqual(contribution.status, ContributionStatus.DISPUTED)


class ClientConfirmationTests(TestCase):
    """T1 path 1: the client / maître d'ouvrage counter-signs a contribution."""

    def setUp(self):
        self.company = make_company()
        self.project = make_project(self.company)
        self.contribution = declare_contributor(
            self.project,
            email=self.company.email,
            role_type=RoleType.DIRECTOR,
            contribution_bullets="- Led the study",
            added_by=self.company,
            confirmation_source=ConfirmationSource.CLIENT,
        )

    def test_client_path_requires_client_source(self):
        expert = make_expert()
        other = linked_contribution(self.company, expert, project=self.project)
        with self.assertRaises(InvalidTransitionError):
            request_client_confirmation(other, self.company, client_email="client@mo.org")

    def test_only_publisher_can_request_client_confirmation(self):
        stranger = make_company(username="stranger", email="s@example.com")
        with self.assertRaises(PermissionDeniedError):
            request_client_confirmation(self.contribution, stranger, client_email="client@mo.org")

    def test_client_confirm_certifies_with_token(self):
        mail.outbox.clear()
        token = request_client_confirmation(
            self.contribution, self.company, client_email="client@mo.org"
        )
        self.assertIsNotNone(token)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Confirmez en tant que client / maître d'ouvrage", mail.outbox[0].body)
        self.assertEqual(claim_client_contribution_token(token), self.contribution)

        confirm_by_client(self.contribution, token)
        self.contribution.refresh_from_db()
        self.assertTrue(self.contribution.is_certified)
        self.assertEqual(self.contribution.confirmed_by, ConfirmationSource.CLIENT)
        self.assertIsNone(self.contribution.client_confirm_token)

    def test_token_is_single_use(self):
        token = request_client_confirmation(
            self.contribution, self.company, client_email="client@mo.org"
        )
        confirm_by_client(self.contribution, token)
        with self.assertRaises(PermissionDeniedError):
            confirm_by_client(self.contribution, token)
        self.assertIsNone(claim_client_contribution_token(token))


class AdjustmentCycleTests(TestCase):
    """Rule 4: adjustments re-trigger validation by the company."""

    def setUp(self):
        self.company = make_company()
        self.expert = make_expert()

    def test_adjustment_returns_to_pending_for_company(self):
        contribution = linked_contribution(self.company, self.expert)
        adjust_contribution(contribution, self.expert, contribution_bullets="- Actually did more")
        contribution.refresh_from_db()
        self.assertEqual(contribution.status, ContributionStatus.PENDING_CONFIRMATION)
        self.assertTrue(contribution.pending_company_validation)
        self.assertEqual(contribution.contribution_bullets, "- Actually did more")

    def test_company_cannot_approve_without_pending_adjustment(self):
        contribution = linked_contribution(self.company, self.expert)
        with self.assertRaises(InvalidTransitionError):
            approve_adjustment(contribution, self.company)

    def test_full_adjustment_cycle_ends_certified(self):
        contribution = linked_contribution(self.company, self.expert)
        adjust_contribution(contribution, self.expert, contribution_bullets="- Adjusted bullets")
        mail.outbox.clear()
        approve_adjustment(contribution, self.company)
        contribution.refresh_from_db()
        self.assertTrue(contribution.is_certified)
        self.assertFalse(contribution.pending_company_validation)

    def test_third_party_cannot_approve(self):
        contribution = linked_contribution(self.company, self.expert)
        adjust_contribution(contribution, self.expert, contribution_bullets="- Adjusted")
        other_company = make_company(username="other", email="other@corp.com")
        with self.assertRaises(PermissionDeniedError):
            approve_adjustment(contribution, other_company)

    def test_adjusting_a_certified_contribution_reopens_cycle_rule8(self):
        contribution = linked_contribution(self.company, self.expert)
        confirm_as_is(contribution, self.expert)
        adjust_contribution(
            contribution, self.expert, contribution_bullets="- Post-certification fix"
        )
        contribution.refresh_from_db()
        self.assertEqual(contribution.status, ContributionStatus.PENDING_CONFIRMATION)
        self.assertIsNone(contribution.confirmed_at)


class ArbitrationTests(TestCase):
    """Rule 7: admins arbitrate disputes: the only human intervention."""

    def setUp(self):
        self.company = make_company()
        self.expert = make_expert()
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@urbantrack.africa", password="Adm!nPass1"
        )

    def test_non_staff_cannot_arbitrate(self):
        contribution = linked_contribution(self.company, self.expert)
        dispute_contribution(contribution, self.expert, reason="Contested")
        with self.assertRaises(PermissionDeniedError):
            resolve_dispute(contribution, self.expert, outcome="confirm")

    def test_arbitration_outcomes(self):
        contribution = linked_contribution(self.company, self.expert)
        dispute_contribution(contribution, self.expert, reason="Contested")

        resolve_dispute(contribution, self.admin, outcome="return_to_expert", note="clarify")
        self.assertEqual(contribution.status, ContributionStatus.PENDING_CONFIRMATION)

        dispute_contribution(contribution, self.expert, reason="Still contested")
        resolve_dispute(contribution, self.admin, outcome="confirm")
        contribution.refresh_from_db()
        self.assertTrue(contribution.is_certified)

    def test_arbitration_only_on_disputed(self):
        contribution = linked_contribution(self.company, self.expert)
        with self.assertRaises(InvalidTransitionError):
            resolve_dispute(contribution, self.admin, outcome="confirm")


class InvitationLifecycleTests(TestCase):
    """Rule 6: reminders capped at 2, then expiry."""

    def setUp(self):
        self.company = make_company()
        self.project = make_project(self.company)
        self.contribution = declare_contributor(
            self.project,
            email="ghost@example.com",
            role_type=RoleType.SPECIALIST,
            contribution_bullets="x",
            added_by=self.company,
        )
        mail.outbox.clear()
        self.invitation = notify_contributions_for_project(self.project)["invitations"][0]

    def test_mark_opened_moves_status_chain(self):
        mark_invitation_opened(self.invitation)
        self.invitation.refresh_from_db()
        self.contribution.refresh_from_db()
        self.assertEqual(self.invitation.status, InvitationStatus.OPENED)
        self.assertEqual(self.contribution.status, ContributionStatus.PENDING_CONFIRMATION)

    def test_reminder_budget_enforced(self):
        send_invitation_reminder(self.invitation)
        send_invitation_reminder(self.invitation)
        self.assertEqual(self.invitation.reminder_count, 2)
        self.assertEqual(len(mail.outbox), 3)  # invite + 2 reminders
        with self.assertRaises(InvalidTransitionError):
            send_invitation_reminder(self.invitation)

    def test_expire_stale_marks_overdue_only(self):
        from datetime import timedelta

        from django.utils import timezone

        fresh_contribution = declare_contributor(
            self.project,
            email="fresh@example.com",
            role_type=RoleType.ASSISTANT,
            contribution_bullets="x",
            added_by=self.company,
        )
        fresh = ExpertInvitation.objects.create(
            contribution=fresh_contribution, email="fresh@example.com"
        )
        stale_contribution = declare_contributor(
            self.project,
            email="stale@example.com",
            role_type=RoleType.ASSISTANT,
            contribution_bullets="x",
            added_by=self.company,
        )
        stale = ExpertInvitation.objects.create(
            contribution=stale_contribution,
            email="stale@example.com",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        updated = expire_stale_invitations()
        self.assertGreaterEqual(updated, 1)
        stale.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(stale.status, InvitationStatus.EXPIRED)
        self.assertEqual(fresh.status, InvitationStatus.SENT)

    def test_expired_token_yields_nothing_on_landing_lookup(self):
        from datetime import timedelta

        from django.utils import timezone

        self.invitation.expires_at = timezone.now() - timedelta(days=1)
        self.invitation.save(update_fields=["expires_at"])
        self.assertIsNone(get_by_token(self.invitation.token))
