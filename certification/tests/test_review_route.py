"""
Tests of the registered-expert review route (dashboard entry point).

Registered experts never receive a magic-link token: they act on their
declarations from /certification/contributions/<pk>/review/, guarded by
account identity.
"""

from django.test import TestCase
from django.urls import reverse

from projects.services import publish_project
from projects.tests.test_models import make_company, make_project

from ..models import ContributionStatus
from ..services import declare_contributor
from .test_models import make_expert


class ContributionReviewTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.expert = make_expert(username="awa", email="awa@example.com")
        self.project = make_project(self.company)
        self.contribution = declare_contributor(
            self.project,
            email="awa@example.com",
            role_type="director",
            contribution_bullets="Led the feasibility study",
            added_by=self.company,
        )
        publish_project(self.project)
        self.url = reverse(
            "certification:contribution_review", args=[self.contribution.pk]
        )

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_named_expert_sees_declaration_and_actions(self):
        self.client.force_login(self.expert)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Led the feasibility study", content)
        self.assertIn("Confirm as-is", content)

    def test_other_users_get_403_even_when_logged_in(self):
        stranger = make_expert(username="stranger", email="stranger@example.com")
        self.client.force_login(stranger)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_confirm_through_review_certifies(self):
        self.client.force_login(self.expert)
        response = self.client.post(self.url, {"action": "confirm"})
        self.assertEqual(response.status_code, 302)
        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.status, ContributionStatus.CONFIRMED)

    def test_dispute_without_reason_shows_error_and_keeps_state(self):
        self.client.force_login(self.expert)
        response = self.client.post(self.url, {"action": "dispute", "reason": ""})
        self.assertRedirects(response, self.url)
        self.contribution.refresh_from_db()
        self.assertNotEqual(self.contribution.status, ContributionStatus.DISPUTED)
