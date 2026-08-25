"""
CV generator tests: multi-skin rendering, certification-only data,
builder/preview/pdf routes and the portfolio self-edit screen.
"""


from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from certification.services import adjust_contribution, declare_contributor
from projects.models import Project, ProjectVisibility
from projects.services import publish_project

from .engine import CV_SKINS, cv_context_from_user, demo_cv_context, render_cv_html


def make_expert(username="cv.expert", email="cv@expert.com"):
    return User.objects.create_user(
        username=username,
        email=email,
        password="S3cret!pass",
        role=Role.EXPERT,
        first_name="Moussa",
        last_name="Fall",
    )


def make_company():
    return User.objects.create_user(
        username="cv.corp",
        email="cv@corp.com",
        password="S3cret!pass",
        role=Role.COMPANY,
        organisation_name="CV Corp",
    )


class EngineTests(TestCase):
    def test_all_skins_render_in_both_languages(self):
        context = demo_cv_context()
        for skin in CV_SKINS:
            for lang in ("fr", "en"):
                html = render_cv_html(context, skin, lang)
                self.assertIn("<!DOCTYPE html>", html)
                self.assertIn("Aminata Sow", html)

    def test_unknown_skin_rejected(self):
        with self.assertRaises(ValueError):
            render_cv_html(demo_cv_context(), "nope", "en")


class CertificationOnlyDataTests(TestCase):
    """The CV contract: confirmed contributions only, nothing else."""

    def setUp(self):
        self.company = make_company()
        self.expert = make_expert()
        self.project = Project.objects.create(
            official_name="Engine project",
            description="d",
            deliverables="a\nb",
            duration_start="2024-05-01",
            budget=5000,
            client_name="Client X",
            visibility=ProjectVisibility.PUBLIC,
            published_by=self.company,
        )
        publish_project(self.project)

    def test_only_confirmed_contributions_appear(self):
        from certification.services import confirm_as_is

        declare_contributor(
            self.project,
            email=self.expert.email,
            role_type="specialist",
            contribution_bullets="Pending bullets",
            added_by=self.company,
        )  # stays pending: the expert never confirmed it
        confirmed = declare_contributor(
            self.project,
            email=self.expert.email,
            role_type="manager",
            contribution_bullets="Confirmed work",
            added_by=self.company,
        )
        confirm_as_is(confirmed, self.expert)

        context = cv_context_from_user(self.expert, "en")
        titles = [exp["title"] for exp in context["experiences"]]
        bullets = [b for exp in context["experiences"] for b in exp["bullets"]]
        self.assertEqual(titles.count("Engine project"), 1)
        self.assertIn("Confirmed work", bullets)
        self.assertNotIn("Pending bullets", bullets)

    def test_adjustment_hidden_until_company_validates(self):
        contribution = declare_contributor(
            self.project,
            email=self.expert.email,
            role_type="director",
            contribution_bullets="Original wording",
            added_by=self.company,
        )
        adjust_contribution(
            contribution, self.expert, contribution_bullets="Adjusted wording"
        )
        html = render_cv_html(cv_context_from_user(self.expert, "en"),
                              "world_bank", "en")
        self.assertNotIn("Adjusted wording", html)
        self.assertNotIn("Original wording", html)


class CvViewTests(TestCase):
    def setUp(self):
        self.expert = make_expert()
        self.client = self.client_class()

    def test_builder_requires_login_and_expert_role(self):
        response = self.client.get(reverse("cv_generator:builder"))
        self.assertEqual(response.status_code, 302)
        company = make_company()
        self.client.force_login(company)
        self.assertEqual(
            self.client.get(reverse("cv_generator:builder")).status_code, 403
        )

    def test_builder_lists_skins_and_examples(self):
        self.client.force_login(self.expert)
        response = self.client.get(reverse("cv_generator:builder"))
        self.assertContains(response, "Harvard")
        self.assertContains(response, "AFD")
        self.assertContains(response, "World Bank")
        self.assertContains(response, "example=1")

    def test_preview_and_pdf_endpoints(self):
        self.client.force_login(self.expert)
        preview = self.client.get(reverse("cv_generator:preview", args=["afd"]))
        self.assertEqual(preview.status_code, 200)
        self.assertIn("Moussa Fall", preview.content.decode())

        pdf_response = self.client.get(
            reverse("cv_generator:pdf", args=["academic_harvard_mit"])
        )
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")

    def test_profile_edit_updates_skills_and_trainings(self):
        from accounts.portfolio_forms import SkillsForm

        profile = self.expert.expert_profile
        form = SkillsForm(data={"skills": "GIS analysis, donor reporting, GIS Analysis"})
        self.assertTrue(form.is_valid())
        form.save(profile)
        names = {s.name for s in profile.skills.all()}
        self.assertEqual(len(names), 2)  # duplicates collapsed case-insensitively

        self.client.force_login(self.expert)
        response = self.client.post(
            reverse("accounts:profile_edit"),
            {
                "headline": "Urban planner",
                "bio": "Twelve years of field work.",
                "city": "Dakar",
                "country": "Senegal",
                "cv_template": "afd",
                "skills": "GIS analysis, donor reporting",
                "trainings-TOTAL_FORMS": "2",
                "trainings-INITIAL_FORMS": "0",
                "trainings-MIN_NUM_FORMS": "0",
                "trainings-MAX_NUM_FORMS": "1000",
                "trainings-0-title": "MSc Urban Engineering",
                "trainings-0-institution": "EPFL",
                "trainings-0-year": "2012",
                "trainings-1-title": "",
                "trainings-1-institution": "",
                "trainings-1-year": "",
            },
        )
        self.assertRedirects(response, reverse("accounts:profile_edit"))
        profile.refresh_from_db()
        self.assertEqual(profile.headline, "Urban planner")
        self.assertTrue(profile.trainings.filter(title="MSc Urban Engineering").exists())
