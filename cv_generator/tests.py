"""
CV generator tests: multi-skin rendering, certification-only data,
builder/preview/pdf routes and the portfolio self-edit screen.
"""

import re
from pathlib import Path

from django.test import TestCase
from django.urls import reverse

from accounts.models import Company, Role, User
from certification.services import adjust_contribution, declare_contributor
from projects import models as projects_models
from projects.models import Project, ProjectVisibility
from projects.services import publish_project

from .engine import (
    CV_CONTRACTS,
    CV_SKINS,
    FALLBACK_LANG,
    LABELS,
    CvContextError,
    LabelResolver,
    cv_context_from_user,
    demo_cv_context,
    load_cv_labels,
    render_cv_docx,
    render_cv_html,
    validate_cv_context,
)

_company_seq = 0


def make_expert(username="cv.expert", email="cv@expert.com"):
    global _company_seq
    _company_seq += 1
    company = Company.objects.create(name=f"CV Expert Corp {_company_seq}")
    return User.objects.create_user(
        username=username,
        email=email,
        password="S3cret!pass",
        role=Role.USER,
        company=company,
        email_confirmed=True,
        first_name="Moussa",
        last_name="Fall",
    )


def make_company():
    global _company_seq
    _company_seq += 1
    company = Company.objects.create(name=f"CV Corp {_company_seq}")
    return User.objects.create_user(
        username="cv.corp",
        email="cv@corp.com",
        password="S3cret!pass",
        role=Role.USER,
        email_confirmed=True,
        company=company,
    )


def _empty_formsets(exclude=()):
    """Management-form rows for the six portfolio formsets when unused."""
    management = {}
    for prefix in (
        "trainings",
        "positions",
        "mandates",
        "publications",
        "teaching_entries",
        "media_appearances",
    ):
        if prefix in exclude:
            continue
        management[f"{prefix}-TOTAL_FORMS"] = "0"
        management[f"{prefix}-INITIAL_FORMS"] = "0"
        management[f"{prefix}-MIN_NUM_FORMS"] = "0"
        management[f"{prefix}-MAX_NUM_FORMS"] = "1000"
    return management


class LabelDictionaryTests(TestCase):
    """T18: every label used in any CV template must be declared in the shared
    FR/EN dictionary (docs/cv-labels.i18n.json); FR/EN stay symmetric; a missing
    label in the requested language falls back to English with a logged warning
    — never a raw key, never broken text."""

    TEMPLATE_DIR = Path("templates") / "cv"

    def _used_keys(self, filename):
        text = (Path(self.TEMPLATE_DIR) / filename).read_text(encoding="utf-8")
        return set(re.findall(r"labels\.([A-Za-z_][A-Za-z0-9_]*)", text))

    def test_every_label_key_used_by_templates_is_declared(self):
        declared = set(load_cv_labels()[FALLBACK_LANG])
        missing = {}
        for html in sorted(Path(self.TEMPLATE_DIR).glob("*.html")):
            undeclared = self._used_keys(html.name) - declared
            if undeclared:
                missing[html.name] = sorted(undeclared)
        self.assertEqual(
            missing,
            {},
            "labels used by a template but missing from cv-labels.i18n.json",
        )

    def test_fr_and_en_dictionaries_are_symmetric(self):
        dictionaries = load_cv_labels()
        self.assertEqual(set(dictionaries["fr"]), set(dictionaries["en"]))

    def test_missing_fr_key_falls_back_to_english_with_warning(self):
        fr = {"profile": "Profil"}
        en = {"profile": "Profile", "training": "Training"}
        with self.assertLogs("cv_generator.engine", level="WARNING") as captured:
            resolver = LabelResolver("fr", fr, en)
            self.assertEqual(resolver["training"], "Training")
        self.assertTrue(any("training" in line for line in captured.output))


class DataContractTests(TestCase):
    """T20: every CV template declares a data contract, and the rendering
    engine enforces it with explicit errors on wrong-typed or missing fields."""

    TEMPLATE_DIR = Path("templates") / "cv"

    def test_every_skin_has_a_registered_contract(self):
        self.assertEqual(set(CV_SKINS), set(CV_CONTRACTS))

    def test_canonical_contexts_validate_against_classic_skins(self):
        expert = make_expert()
        real = cv_context_from_user(expert, "en")
        demo = demo_cv_context("fr")
        for skin in CV_SKINS:
            validate_cv_context(real, skin)
            validate_cv_context(demo, skin)

    def test_unknown_template_rejected(self):
        with self.assertRaises(CvContextError) as caught:
            validate_cv_context(demo_cv_context(), "ghost")
        self.assertIn("ghost", str(caught.exception))

    def test_wrong_field_type_raises_explicit_error(self):
        broken = demo_cv_context()
        broken["trust_score"] = "eighty-seven"
        with self.assertRaises(CvContextError) as caught:
            validate_cv_context(broken, "afd")
        self.assertIn("trust_score", str(caught.exception))
        self.assertIn("int", str(caught.exception))

    def test_missing_required_field_raises_explicit_error(self):
        broken = demo_cv_context()
        del broken["experiences"]
        with self.assertRaises(CvContextError) as caught:
            validate_cv_context(broken, "world_bank")
        self.assertIn("experiences", str(caught.exception))

    def test_rendering_with_bad_data_raises_not_broken_output(self):
        broken = demo_cv_context()
        broken["is_demo"] = "yes"
        with self.assertRaises(CvContextError):
            render_cv_html(broken, "academic_harvard_mit", "en")

    def test_world_bank_new_context_validates(self):
        minimal = {
            "identity": {"name": "Aminata Sow"},
            "bio": None,
            "strengths": [],
            "indicators_list": [],
            "expertise_domains": [],
            "skills": [],
            "trainings": [],
            "other_trainings": [],
            "associations": [],
            "countries": [],
            "languages": [],
            "positions": [],
            "projects": [],
            "publications": [],
            "teaching": {},
            "media": [],
            "miscellaneous": [],
            "certification": None,
            "trust_score": 87,
            "is_demo": True,
        }
        validate_cv_context(minimal, "world_bank_new")
        minimal["teaching"] = ["not", "a", "dict"]
        with self.assertRaises(CvContextError) as caught:
            validate_cv_context(minimal, "world_bank_new")
        self.assertIn("teaching", str(caught.exception))


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

    def test_docx_export_is_editable_word_document(self):
        from io import BytesIO

        from docx import Document

        docx = render_cv_docx(demo_cv_context("en"), "world_bank", "en")
        self.assertTrue(docx.startswith(b"PK"))
        document = Document(BytesIO(docx))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        self.assertIn("Aminata Sow", text)
        self.assertIn("Certified professional experience", text)
        self.assertIn("Dakar Corniche Ouest redevelopment", text)


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
        adjust_contribution(contribution, self.expert, contribution_bullets="Adjusted wording")
        html = render_cv_html(cv_context_from_user(self.expert, "en"), "world_bank", "en")
        self.assertNotIn("Adjusted wording", html)
        self.assertNotIn("Original wording", html)


class CvViewTests(TestCase):
    def setUp(self):
        self.expert = make_expert()
        self.client = self.client_class()

    def test_builder_requires_login(self):
        response = self.client.get(reverse("cv_generator:builder"))
        self.assertEqual(response.status_code, 302)

    def test_builder_lists_skins_and_examples(self):
        self.client.force_login(self.expert)
        response = self.client.get(reverse("cv_generator:builder"))
        self.assertContains(response, "Académique")
        self.assertContains(response, "AFD")
        self.assertContains(response, "Banque mondiale")
        self.assertContains(response, "example=1")
        self.assertNotContains(response, "Language:")
        self.assertNotContains(response, "Generate my CV")

    def test_preview_pdf_and_docx_endpoints(self):
        self.client.force_login(self.expert)
        preview = self.client.get(reverse("cv_generator:preview", args=["afd"]))
        self.assertEqual(preview.status_code, 200)
        self.assertIn("Moussa Fall", preview.content.decode())

        pdf_response = self.client.get(reverse("cv_generator:pdf", args=["academic_harvard_mit"]))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")

        docx_response = self.client.get(reverse("cv_generator:docx", args=["world_bank"]))
        self.assertEqual(docx_response.status_code, 200)
        self.assertEqual(
            docx_response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertIn(".docx", docx_response["Content-Disposition"])

    def test_targeted_cv_filters_selected_projects(self):
        self.client.force_login(self.expert)
        company_one = User.objects.create_user(
            username="cv.company.one",
            email="cv.company.one@example.com",
            password="S3cret!pass",
            role=Role.USER,
            company=Company.objects.create(name="Target Company One"),
            email_confirmed=True,
        )
        company_two = User.objects.create_user(
            username="cv.company.two",
            email="cv.company.two@example.com",
            password="S3cret!pass",
            role=Role.USER,
            company=Company.objects.create(name="Target Company Two"),
            email_confirmed=True,
        )
        project_one = Project.objects.create(
            official_name="Target project A",
            description="d",
            deliverables="a\nb",
            duration_start="2024-01-01",
            budget=5000,
            client_name="Client X",
            visibility=ProjectVisibility.PUBLIC,
            published_by=company_one,
        )
        project_two = Project.objects.create(
            official_name="Target project B",
            description="d",
            deliverables="a\nb",
            duration_start="2024-01-01",
            budget=5000,
            client_name="Client X",
            visibility=ProjectVisibility.PUBLIC,
            published_by=company_two,
        )
        publish_project(project_one)
        publish_project(project_two)

        from certification.services import confirm_as_is

        contribution_one = declare_contributor(
            project_one,
            email=self.expert.email,
            role_type="manager",
            contribution_bullets="Selected contribution",
            added_by=company_one,
        )
        confirm_as_is(contribution_one, self.expert)

        contribution_two = declare_contributor(
            project_two,
            email=self.expert.email,
            role_type="manager",
            contribution_bullets="Unselected contribution",
            added_by=company_two,
        )
        confirm_as_is(contribution_two, self.expert)

        response = self.client.get(
            reverse("cv_generator:preview", args=["afd"]),
            {"projects": [project_one.id]},
        )
        html = response.content.decode()
        self.assertIn("Target project A", html)
        self.assertNotIn("Target project B", html)

        builder = self.client.get(reverse("cv_generator:builder"), {"projects": [project_one.id]})
        self.assertContains(builder, f"projects={project_one.id}")

    def test_profile_edit_updates_skills_and_trainings(self):
        from accounts.portfolio_forms import SkillsForm

        profile = self.expert.expert_profile
        form = SkillsForm(data={"skills": "GIS analysis, donor reporting, GIS Analysis"})
        self.assertTrue(form.is_valid())
        form.save(profile)
        names = {s.name for s in profile.skills.all()}
        self.assertEqual(len(names), 2)  # duplicates collapsed case-insensitively

        payload = {
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
        }
        payload.update(_empty_formsets(exclude=("trainings",)))
        self.client.force_login(self.expert)
        response = self.client.post(reverse("accounts:profile_edit"), payload)
        self.assertRedirects(response, reverse("accounts:profile_edit"))
        profile.refresh_from_db()
        self.assertEqual(profile.headline, "Urban planner")
        self.assertTrue(profile.trainings.filter(title="MSc Urban Engineering").exists())


class DeclaredSectionsViewTests(TestCase):
    """T4/T4a: the portfolio screen saves positions, mandates, publications,
    teaching, media, strengths, countries, languages and misc."""

    def setUp(self):
        self.expert = make_expert()
        self.profile = self.expert.expert_profile
        self.client.force_login(self.expert)

    def test_declared_blocks_are_saved(self):
        payload = {
            "headline": "Urban planner",
            "bio": "Bio.",
            "nationality": "Senegalese",
            "phone": "+221 77 000 00 00",
            "birth_date": "1980-05-01",
            "city": "Dakar",
            "country": "Senegal",
            "cv_template": "afd",
            "strengths": "Donor relations, GIS",
            "countries_of_intervention": "Senegal, Benin",
            "languages": "French, fluent, fluent, native\nEnglish, fluent, fluent, fluent",
            "misc": "Member, Ordre des architectes",
            "skills": "GIS",
            # positions
            "positions-TOTAL_FORMS": "2",
            "positions-INITIAL_FORMS": "0",
            "positions-MIN_NUM_FORMS": "0",
            "positions-MAX_NUM_FORMS": "1000",
            "positions-0-employer": "ACME",
            "positions-0-function": "Director of studies",
            "positions-0-date_start": "2018-01-01",
            "positions-0-date_end": "",
            "positions-0-description": "Leading the research centre.",
            "positions-1-employer": "",
            "positions-1-function": "",
            "positions-1-date_start": "",
            "positions-1-date_end": "",
            "positions-1-description": "",
            # mandate
            "mandates-TOTAL_FORMS": "1",
            "mandates-INITIAL_FORMS": "0",
            "mandates-MIN_NUM_FORMS": "0",
            "mandates-MAX_NUM_FORMS": "1000",
            "mandates-0-name": "OAI",
            "mandates-0-role": "Board member",
            "mandates-0-year_start": "2021",
            "mandates-0-year_end": "",
            # publication
            "publications-TOTAL_FORMS": "1",
            "publications-INITIAL_FORMS": "0",
            "publications-MIN_NUM_FORMS": "0",
            "publications-MAX_NUM_FORMS": "1000",
            "publications-0-title": "Villes secondaires",
            "publications-0-venue": "Revue X",
            "publications-0-year": "2022",
            # teaching
            "teaching_entries-TOTAL_FORMS": "1",
            "teaching_entries-INITIAL_FORMS": "0",
            "teaching_entries-MIN_NUM_FORMS": "0",
            "teaching_entries-MAX_NUM_FORMS": "1000",
            "teaching_entries-0-title": "Urban economics",
            "teaching_entries-0-institution": "UCAD",
            "teaching_entries-0-year": "2019",
            # media
            "media_appearances-TOTAL_FORMS": "1",
            "media_appearances-INITIAL_FORMS": "0",
            "media_appearances-MIN_NUM_FORMS": "0",
            "media_appearances-MAX_NUM_FORMS": "1000",
            "media_appearances-0-title": "RFI interview",
            "media_appearances-0-outlet": "RFI",
            "media_appearances-0-year": "2021",
            "media_appearances-0-url": "",
            # trainings unused too
            "trainings-TOTAL_FORMS": "0",
            "trainings-INITIAL_FORMS": "0",
            "trainings-MIN_NUM_FORMS": "0",
            "trainings-MAX_NUM_FORMS": "1000",
        }
        response = self.client.post(reverse("accounts:profile_edit"), payload)
        self.assertRedirects(response, reverse("accounts:profile_edit"))

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.nationality, "Senegalese")
        self.assertEqual(self.profile.strengths, ["Donor relations", "GIS"])
        self.assertEqual(self.profile.countries_of_intervention, ["Senegal", "Benin"])
        self.assertEqual(self.profile.languages[0]["name"], "French")
        self.assertEqual(self.profile.languages[0]["spoken"], "fluent")
        self.assertEqual(self.profile.misc, "Member, Ordre des architectes")

        position = self.profile.positions.get()
        self.assertEqual(position.employer, "ACME")
        self.assertIsNone(position.date_end)

        mandate = self.profile.mandates.get()
        self.assertEqual(mandate.name, "OAI")
        publication = self.profile.publications.get()
        self.assertEqual(publication.title, "Villes secondaires")
        teaching = self.profile.teaching_entries.get()
        self.assertEqual(teaching.title, "Urban economics")
        media = self.profile.media_appearances.get()
        self.assertEqual(media.title, "RFI interview")

    def test_duplicate_language_lines_are_collapsed(self):
        payload = {
            "cv_template": "afd",
            "languages": "French, fluent, fluent, native\nFRENCH, fluent, fluent, native",
            "skills": "",
        }
        payload.update(_empty_formsets())
        response = self.client.post(reverse("accounts:profile_edit"), payload)
        self.assertRedirects(response, reverse("accounts:profile_edit"))
        self.profile.refresh_from_db()
        self.assertEqual(len(self.profile.languages), 1)


class DeclaredContextEngineTests(TestCase):
    """T4/T5: the CV context carries declared sections only when filled and the
    skins always render them under the 'declared' marker + legend."""

    def setUp(self):
        self.expert = make_expert()
        self.profile = self.expert.expert_profile

    def test_empty_profile_has_no_declared_sections(self):
        context = cv_context_from_user(self.expert, "en")
        self.assertFalse(context["has_declared"])
        for key in ("positions", "mandates", "publications", "teaching", "media"):
            self.assertEqual(context["declared"][key], [])

    def test_declared_blocks_flow_into_context(self):
        from datetime import date

        from accounts.models import Position

        Position.objects.create(
            profile=self.profile,
            employer="ACME",
            function="Director",
            date_start=date(2018, 1, 1),
        )
        self.profile.strengths = ["Donor relations"]
        self.profile.languages = [{"name": "French", "read": "fluent"}]
        self.profile.countries_of_intervention = ["Senegal"]
        self.profile.save()

        context = cv_context_from_user(self.expert, "en")
        self.assertTrue(context["has_declared"])
        self.assertEqual(context["declared"]["positions"][0]["employer"], "ACME")
        self.assertEqual(context["strengths"], ["Donor relations"])
        self.assertEqual(context["languages"][0]["name"], "French")
        self.assertEqual(context["identity"]["nationality"], "")

    def test_skins_render_declared_marker_and_legend(self):
        from datetime import date

        from accounts.models import Position

        Position.objects.create(
            profile=self.profile,
            employer="ACME",
            function="Director",
            date_start=date(2018, 1, 1),
        )
        for skin in CV_SKINS:
            for lang in ("fr", "en"):
                html = render_cv_html(cv_context_from_user(self.expert, lang), skin, lang)
                self.assertIn("declared-legend", html)
                self.assertIn(LABELS[lang]["declared"], html)

    def test_empty_context_skips_declared_section_entirely(self):
        for skin in CV_SKINS:
            html = render_cv_html(cv_context_from_user(self.expert, "en"), skin, "en")
            self.assertNotIn('<section class="declared">', html)


class CertifiedIndicatorsTests(TestCase):
    """T7: the certified synthesis indicators are computed from the confirmed
    contributions only and rendered as the 'indicateurs certifiés' block."""

    def setUp(self):
        self.company = make_company()
        self.expert = make_expert()
        self.profile = self.expert.expert_profile

    def _project(self, official_name, start, end=None, country=None, funder=None):
        project = Project.objects.create(
            official_name=official_name,
            description="d",
            deliverables="a\nb",
            duration_start=start,
            duration_end=end,
            budget=5000,
            client_name="Client X",
            visibility=ProjectVisibility.PUBLIC,
            published_by=self.company,
            country=country,
            funder=funder,
        )
        publish_project(project)
        return project

    def _confirm(self, project, role_type, bullets="Certified work"):
        from certification.services import confirm_as_is

        contribution = declare_contributor(
            project,
            email=self.expert.email,
            role_type=role_type,
            contribution_bullets=bullets,
            added_by=self.company,
        )
        confirm_as_is(contribution, self.expert)
        return contribution

    def test_indicators_computed_from_confirmed_only(self):
        country = projects_models.Country.objects.create(name="Senegal")
        funder = projects_models.Funder.objects.create(name="AFD")
        p1 = self._project(
            "Sanitation programme", "2020-01-01", "2023-12-31", country=country, funder=funder
        )
        self._confirm(p1, "manager", "Led the programme")
        self._confirm(p1, "specialist", "Technical support")
        p2 = self._project(
            "Mali urban mobility",
            "2015-06-01",
            "2024-12-31",
            country=projects_models.Country.objects.create(name="Mali"),
        )
        self._confirm(p2, "director", "Directed the study")
        # A pending, unconfirmed contribution must NOT count.
        declare_contributor(
            p1,
            email=self.expert.email,
            role_type="assistant",
            contribution_bullets="Pending",
            added_by=self.company,
        )

        indicators = self.profile.synthesis_indicators()
        self.assertEqual(indicators["projects"], 2)  # distinct, p1 counted once
        self.assertEqual(indicators["contributions"], 3)
        self.assertEqual(indicators["countries"], 2)
        self.assertEqual(indicators["donor_programmes"], 1)
        # earliest start 2015-06-01 → latest end 2024-12-31 ≈ 9.5 years
        self.assertEqual(indicators["years_experience"], 9)

    def test_open_ended_projects_measure_up_to_today(self):
        self._confirm(self._project("Ongoing works", "2022-03-01"), "manager")
        indicators = self.profile.synthesis_indicators()
        self.assertGreaterEqual(indicators["years_experience"], 1)

    def test_empty_profile_has_no_indicator_items(self):
        context = cv_context_from_user(self.expert, "en")
        self.assertFalse(context["indicators"]["has_indicators"])
        self.assertEqual(context["indicators"]["items"], [])
        self.assertEqual(context["indicators"]["values"]["projects"], 0)

    def test_skins_render_the_indicator_block(self):
        country = projects_models.Country.objects.create(name="Senegal")
        self._confirm(
            self._project("Sanitation programme", "2020-01-01", "2023-12-31", country=country),
            "manager",
        )
        for skin in CV_SKINS:
            for lang in ("fr", "en"):
                html = render_cv_html(cv_context_from_user(self.expert, lang), skin, lang)
                self.assertIn('class="indicator-block"', html)
                self.assertIn(LABELS[lang]["indicators"], html)

    def test_empty_context_skips_the_indicator_block(self):
        for skin in CV_SKINS:
            html = render_cv_html(cv_context_from_user(self.expert, "en"), skin, "en")
            self.assertNotIn('class="indicator-block"', html)

    def test_public_profile_shows_certified_indicators(self):
        country = projects_models.Country.objects.create(name="Senegal")
        funder = projects_models.Funder.objects.create(name="World Bank")
        project = self._project(
            "Sanitation programme", "2020-01-01", "2023-12-31", country=country, funder=funder
        )
        self._confirm(project, "manager")

        url = reverse("accounts:public_profile", args=[self.expert.professional_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Certified indicators")
        self.assertContains(response, "Donor-funded programs")

    def test_public_profile_hides_indicators_when_none(self):
        url = reverse("accounts:public_profile", args=[self.expert.professional_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Certified indicators")
