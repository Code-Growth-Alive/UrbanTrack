"""
HTTP tests for authentication, signup (role-aware), the expert directory
and the role-aware dashboard.
"""

from django.test import TestCase
from django.urls import reverse

from accounts.models import ExpertProfile
from certification.services import confirm_as_is, declare_contributor
from projects.models import ProjectStatus, ProjectVisibility
from projects.tests.test_models import make_company, make_project

from ..models import User


def make_expert_user(email="seydou@example.com", **overrides):
    defaults = dict(
        username=email,
        email=email,
        password="S3cret!pass",
        email_confirmed=True,
        first_name="Seydou",
        last_name="Ba",
    )
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


class SignUpTests(TestCase):
    def test_signup_page_renders_last_name_field(self):
        """The signup form must submit last_name: without it the form never
        validates and signup silently re-renders (regression: field was
        missing from the template while the form required it)."""
        response = self.client.get(reverse("accounts:signup"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('name="last_name"', content)
        self.assertIn('name="first_name"', content)

    def test_signup_creates_account_confirms_and_lands_on_dashboard(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "first_name": "Aminata",
                "last_name": "Sow",
                "email": "aminata@example.com",
                "password1": "S3cret!pass",
                "password2": "S3cret!pass",
            },
        )
        # Fresh signups land on the email-confirmation screen.
        self.assertRedirects(response, reverse("accounts:confirm_email"))
        user = User.objects.get(email="aminata@example.com")
        self.assertTrue(user.is_expert)
        self.assertTrue(ExpertProfile.objects.filter(user=user).exists())
        self.assertTrue(user.professional_id.startswith("OX-"))
        self.assertFalse(user.email_confirmed)
        # Signed in right away.
        self.assertIn("_auth_user_id", self.client.session)

        # Entering the emailed code activates the account and reaches the dashboard.
        response = self.client.post(
            reverse("accounts:confirm_email"), {"code": user.confirmation_code}
        )
        self.assertRedirects(response, reverse("accounts:dashboard"))
        user.refresh_from_db()
        self.assertTrue(user.email_confirmed)

    def test_duplicate_email_rejected(self):
        make_expert_user()
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "first_name": "Copy",
                "last_name": "Cat",
                "email": "seydou@example.com",
                "password1": "S3cret!pass",
                "password2": "S3cret!pass",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(email="seydou@example.com").count(), 1)

    def test_authenticated_users_are_redirected_away(self):
        company = make_company()
        self.client.force_login(company)
        response = self.client.get(reverse("accounts:signup"))
        self.assertRedirects(response, reverse("accounts:dashboard"))


class LogInOutTests(TestCase):
    def setUp(self):
        self.user = make_expert_user()

    def test_login_page_renders_and_accepts_credentials(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "seydou@example.com", "password": "S3cret!pass"},
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Log out")

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 405)
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)


class ExpertDirectoryTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.expert = make_expert_user()

    def test_directory_lists_confirmed_users(self):
        response = self.client.get(reverse("accounts:expert_list"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Seydou Ba", content)
        # Every confirmed account (including the company publisher) is listed.
        self.assertIn(self.company.username, content)

    def test_profile_shows_initials_not_buggy_slices(self):
        response = self.client.get(
            reverse("accounts:public_profile", args=[self.expert.professional_id])
        )
        self.assertContains(response, "SB")

    def test_search_requires_authentication(self):
        response = self.client.get(reverse("accounts:expert_search"), {"q": "sey"})
        self.assertEqual(response.status_code, 403)

    def test_search_matches_name_email_and_oxid(self):
        self.client.force_login(self.company)
        oxid = self.expert.professional_id

        by_name = self.client.get(reverse("accounts:expert_search"), {"q": "Seydou"}).json()
        by_email = self.client.get(reverse("accounts:expert_search"), {"q": "seydou@"}).json()
        by_id = self.client.get(reverse("accounts:expert_search"), {"q": oxid}).json()
        empty = self.client.get(reverse("accounts:expert_search")).json()

        for payload in (by_name, by_email, by_id, empty):
            self.assertIn(
                {"email": "seydou@example.com", "name": "Seydou Ba", "professional_id": oxid},
                payload["results"],
            )


class InitialsPropertyTests(TestCase):
    def test_full_name_initials(self):
        user = make_expert_user(first_name="Awa", last_name="Diop Ndiaye")
        self.assertEqual(user.initials, "AD")

    def test_falls_back_to_username(self):
        user = make_expert_user(username="kofi.mensah@example.com", first_name="", last_name="")
        self.assertEqual(user.initials, "KO")


class DashboardAccessTests(TestCase):
    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertRedirects(response, "/login/?next=/dashboard/", fetch_redirect_response=False)

    def test_signup_lands_on_email_confirmation(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "first_name": "Aminata",
                "last_name": "Sow",
                "email": "aminata@example.com",
                "password1": "S3cret!pass",
                "password2": "S3cret!pass",
            },
        )
        self.assertRedirects(response, reverse("accounts:confirm_email"))


class ExpertDashboardTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.expert = make_expert_user()
        self.project = make_project(self.company)
        self.contribution = declare_contributor(
            self.project,
            email=self.expert.email,
            role_type="manager",
            contribution_bullets="Ran the site supervision",
            added_by=self.company,
        )
        self.client.force_login(self.expert)

    def test_pending_declaration_appears_with_review_link(self):
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.official_name)
        self.assertContains(
            response,
            reverse("certification:contribution_review", args=[self.contribution.pk]),
        )

    def test_confirmed_contribution_moves_to_certified_section(self):
        confirm_as_is(self.contribution, self.expert)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, "Certified track record")
        self.assertContains(response, "Trust score")
        review_url = reverse("certification:contribution_review", args=[self.contribution.pk])
        self.assertNotContains(response, review_url)

    def test_adjusted_wording_hidden_until_company_validates(self):
        from certification.services import adjust_contribution

        adjust_contribution(
            self.contribution,
            self.expert,
            contribution_bullets="Adjusted wording",
        )
        response = self.client.get(reverse("accounts:dashboard"))
        # Still pending overall but awaiting the COMPANY: not reviewable.
        review_url = reverse("certification:contribution_review", args=[self.contribution.pk])
        self.assertNotContains(response, review_url)


class CompanyDashboardTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.other = make_company(username="other", email="other@corp.com")
        self.project = make_project(self.company)
        self.client.force_login(self.company)

    def test_lists_own_projects_with_status_and_manage_links(self):
        make_project(
            self.other,
            official_name="Not mine",
            status=ProjectStatus.PUBLISHED,
            visibility=ProjectVisibility.PUBLIC,
        )
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.official_name)
        self.assertNotContains(response, "Not mine")
        self.assertContains(response, str(self.project.pk) + "/manage/")

    def test_empty_state_points_to_first_publish(self):
        company = make_company(username="fresh", email="fresh@corp.com")
        company.published_projects.all().delete()
        self.client.force_login(company)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, "Publish my first project")

    def test_awaiting_validation_alert_shown_for_company(self):
        expert = User.objects.create_user(
            username="mari",
            email="mari@example.com",
            password="S3cret!pass",
            email_confirmed=True,
        )
        contribution = declare_contributor(
            self.project,
            email=expert.email,
            role_type="specialist",
            contribution_bullets="Initial wording",
            added_by=self.company,
        )
        from certification.services import adjust_contribution

        adjust_contribution(contribution, expert, contribution_bullets="Corrected wording")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, "awaiting your validation")
        self.assertContains(response, "Validate now")
