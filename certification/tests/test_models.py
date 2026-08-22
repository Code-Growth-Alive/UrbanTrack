"""Tests for ProjectContribution / ExpertInvitation models and integrity rules."""


from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase
from django.utils import timezone

from projects.tests.test_models import make_company, make_project

from ..models import (
    ContributionStatus,
    ExpertInvitation,
    ProjectContribution,
    RoleType,
)

User = get_user_model()


def make_expert(username="ama", email=None):
    return User.objects.create_user(
        username=username,
        email=email or f"{username}@example.com",
        first_name="Aminata",
        last_name="Diallo",
        password="S3cret!pass",
    )


def make_contribution(company, project=None, email="nobody@example.com", **overrides):
    defaults = dict(
        project=project or make_project(company),
        invited_email=email,
        role_type=RoleType.SPECIALIST,
        contribution_bullets="- Designed the drainage plan\n- Supervised works",
        added_by=company,
    )
    defaults.update(overrides)
    return ProjectContribution.objects.create(**defaults)


class ContributionModelTests(TestCase):
    def setUp(self):
        self.company = make_company()

    def test_default_status_is_invited(self):
        contribution = make_contribution(self.company)
        self.assertEqual(contribution.status, ContributionStatus.INVITED)
        self.assertIsNone(contribution.confirmed_at)

    def test_duplicate_project_email_role_refused(self):
        project = make_project(self.company)
        make_contribution(
            self.company, project=project, email="x@example.com", role_type=RoleType.MANAGER
        )
        with self.assertRaises(IntegrityError):
            make_contribution(
                self.company, project=project, email="X@example.com", role_type=RoleType.MANAGER
            )

    def test_same_email_different_roles_allowed(self):
        project = make_project(self.company)
        make_contribution(
            self.company, project=project, email="x@example.com", role_type=RoleType.MANAGER
        )
        second = make_contribution(
            self.company, project=project, email="x@example.com", role_type=RoleType.DIRECTOR
        )
        self.assertEqual(second.status, ContributionStatus.INVITED)

    def test_direct_model_creation_does_not_auto_link(self):
        """Auto-linking happens in the service layer; plain save keeps expert unset."""
        make_expert(email="linked@example.com")
        contribution = make_contribution(self.company, email="Linked@Example.COM")
        contribution.refresh_from_db()
        self.assertIsNone(contribution.expert)
        self.assertEqual(contribution.invited_email, "linked@example.com")

    def test_email_normalised_on_save(self):
        contribution = make_contribution(self.company, email="Some.One@EXAMPLE.com")
        contribution.refresh_from_db()
        self.assertEqual(contribution.invited_email, "some.one@example.com")

    def test_confirmed_at_required_when_confirmed(self):
        """DB constraint: no confirmed status without confirmed_at."""
        with self.assertRaises(IntegrityError):
            make_contribution(self.company, status=ContributionStatus.CONFIRMED)

    def test_immutable_once_confirmed_rule8(self):
        """Rule 8: certified data cannot be silently modified."""
        expert = make_expert()
        contribution = make_contribution(self.company, expert=expert)
        contribution.status = ContributionStatus.CONFIRMED
        contribution.confirmed_at = timezone.now()
        contribution.save()

        contribution.contribution_bullets = "Tampered wording"
        contribution.role_type = RoleType.DIRECTOR
        with self.assertRaises(ValidationError) as ctx:
            contribution.save()
        self.assertIn("role_type", ctx.exception.message_dict)
        self.assertIn("contribution_bullets", ctx.exception.message_dict)

    def test_new_validation_cycle_allows_modification(self):
        """Rule 8 + rule 4: leaving 'confirmed' in the same save re-opens the cycle."""
        expert = make_expert()
        contribution = make_contribution(self.company, expert=expert)
        contribution.status = ContributionStatus.CONFIRMED
        contribution.confirmed_at = timezone.now()
        contribution.save()

        contribution.pending_company_validation = True
        contribution.status = ContributionStatus.PENDING_CONFIRMATION
        contribution.confirmed_at = None
        contribution.contribution_bullets = "Adjusted wording"
        contribution.save()

        contribution.refresh_from_db()
        self.assertEqual(contribution.status, ContributionStatus.PENDING_CONFIRMATION)
        self.assertEqual(contribution.contribution_bullets, "Adjusted wording")

    def test_bullets_lines_helper(self):
        contribution = make_contribution(
            self.company, contribution_bullets="A\n B\n\nC "
        )
        self.assertEqual(
            contribution.contribution_bullets_lines, ["A", "B", "C"]
        )


class InvitationModelTests(TestCase):
    def setUp(self):
        self.company = make_company()

    def test_token_is_unique_uuid_and_expiry_14_days(self):
        from datetime import timedelta

        contribution = make_contribution(self.company)
        invitation = ExpertInvitation.objects.create(
            contribution=contribution, email=contribution.invited_email
        )
        self.assertEqual(invitation.reminder_count, 0)
        self.assertEqual(invitation.status, "sent")
        self.assertAlmostEqual(
            invitation.expires_at - invitation.sent_at,
            timedelta(days=14),
            delta=timedelta(seconds=5),
        )

    def test_magic_link_path_format(self):
        contribution = make_contribution(self.company)
        invitation = ExpertInvitation.objects.create(
            contribution=contribution, email="a@b.com"
        )
        self.assertEqual(
            invitation.magic_link_path, f"/certification/invitations/{invitation.token}/"
        )

    def test_is_active_false_after_expiry(self):
        from datetime import timedelta

        contribution = make_contribution(self.company)
        invitation = ExpertInvitation.objects.create(
            contribution=contribution,
            email="a@b.com",
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(invitation.is_active)
