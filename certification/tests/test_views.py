"""
Tests of the magic-link landing (Epic 3 UI) and the expert actions.

These complement the service-level tests by covering the HTTP surface:
token resolution, open tracking, integrated signup, and every action.
"""

from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts.models import ExpertProfile
from projects.services import publish_project
from projects.tests.test_models import make_company, make_project

from ..models import ContributionStatus, InvitationStatus
from ..services import declare_contributor
from .test_models import make_expert

User = get_user_model()


class InvitationFlowTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.project = make_project(self.company)
        self.contribution = declare_contributor(
            self.project,
            email="nadia@example.com",
            role_type="director",
            contribution_bullets="Led the urban design study",
            added_by=self.company,
        )
        publish_project(self.project)
        self.invitation = self.contribution.invitations.get()
        self.url = reverse("certification:invitation_landing", args=[self.invitation.token])

    def signup(self):
        response = self.client.post(
            self.url,
            {
                "action": "signup",
                "first_name": "Nadia",
                "last_name": "Kone",
                "password1": "S3cret!pass",
                "password2": "S3cret!pass",
            },
        )
        # New accounts must confirm their email before acting (6-digit code).
        user = User.objects.get(email="nadia@example.com")
        self.assertFalse(user.email_confirmed)
        confirm = self.client.post(
            reverse("accounts:confirm_email"), {"code": user.confirmation_code}
        )
        self.assertRedirects(confirm, reverse("accounts:dashboard"))
        return response

    def test_unknown_token_returns_friendly_404(self):
        response = self.client.get(reverse("certification:invitation_landing", args=[uuid4()]))
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Ce lien d'invitation n'est plus valide", status_code=404)

    def test_landing_marks_invitation_opened(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.official_name)
        self.assertContains(response, "Confirmer telle quelle")
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, InvitationStatus.OPENED)
        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.status, ContributionStatus.PENDING_CONFIRMATION)

    def test_anonymous_action_redirects_to_login(self):
        response = self.client.post(self.url, {"action": "confirm"})
        self.assertEqual(response.status_code, 302)

    def test_signup_through_landing_creates_linked_account(self):
        response = self.signup()
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="nadia@example.com")
        self.assertTrue(user.is_expert)
        self.assertTrue(ExpertProfile.objects.filter(user=user).exists())
        # Logged in right away.
        response = self.client.post(self.url, {"action": "confirm"})
        self.assertEqual(response.status_code, 302)
        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.status, ContributionStatus.CONFIRMED)
        self.assertEqual(self.contribution.expert, user)
        self.assertIsNotNone(self.contribution.confirmed_at)

    def test_signup_rejects_weak_password_without_creating_account(self):
        response = self.client.post(
            self.url,
            {
                "action": "signup",
                "first_name": "Nadia",
                "last_name": "Kone",
                "password1": "123",
                "password2": "123",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="nadia@example.com").exists())

    def test_adjust_starts_new_validation_cycle(self):
        self.signup()
        response = self.client.post(
            self.url,
            {
                "action": "adjust",
                "role_type": "manager",
                "contribution_bullets": "Co-authored the urban design study",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.status, ContributionStatus.PENDING_CONFIRMATION)
        self.assertTrue(self.contribution.pending_company_validation)
        self.assertEqual(self.contribution.role_type, "manager")

    def test_company_approval_certifies_adjustment(self):
        self.signup()
        self.client.post(
            self.url,
            {
                "action": "adjust",
                "role_type": "manager",
                "contribution_bullets": "Co-authored the urban design study",
            },
        )
        self.client.force_login(self.company)
        manage_url = reverse("projects:manage", args=[self.project.pk])
        response = self.client.post(
            manage_url,
            {"action": "approve", "contribution_pk": self.contribution.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.status, ContributionStatus.CONFIRMED)
        self.assertFalse(self.contribution.pending_company_validation)

    def test_reject_is_terminal(self):
        self.signup()
        response = self.client.post(self.url, {"action": "reject", "reason": "Was not involved."})
        self.assertEqual(response.status_code, 302)
        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.status, ContributionStatus.REJECTED)

    def test_dispute_requires_reason(self):
        self.signup()
        response = self.client.post(self.url, {"action": "dispute", "reason": ""})
        self.assertEqual(response.status_code, 302)
        self.contribution.refresh_from_db()
        self.assertNotEqual(self.contribution.status, ContributionStatus.DISPUTED)

        response = self.client.post(
            self.url,
            {"action": "dispute", "reason": "The wording overstates my role."},
        )
        self.assertEqual(response.status_code, 302)
        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.status, ContributionStatus.DISPUTED)

    def test_mismatched_logged_in_user_cannot_act(self):
        stranger = make_expert(username="other", email="other@example.com")
        self.client.force_login(stranger)
        response = self.client.post(self.url, {"action": "confirm"})
        self.assertRedirects(response, self.url)
        self.contribution.refresh_from_db()
        self.assertNotEqual(self.contribution.status, ContributionStatus.CONFIRMED)


class RegisteredExpertNotificationTests(TestCase):
    """Registered experts are auto-linked: notification path, no invitation."""

    def setUp(self):
        self.company = make_company(username="agl", email="agl@example.com")
        self.expert = make_expert(username="seydou", email="seydou@example.com")
        self.project = make_project(self.company)
        self.contribution = declare_contributor(
            self.project,
            email="seydou@example.com",
            role_type="specialist",
            contribution_bullets="Hydrology modelling",
            added_by=self.company,
        )

    def test_publish_notifies_instead_of_inviting(self):
        publish_project(self.project)
        self.assertEqual(self.contribution.invitations.count(), 0)
        self.assertEqual(len(mail.outbox), 1)  # internal notification email
        self.assertIn("seydou@example.com", mail.outbox[0].to)
