"""T6: donor-format project enrichment — structured country/funder, volume,
personal participation window, phase, thematic tags, wider role list, filters."""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from projects.tests.test_models import make_company, make_project

from ..forms import ProjectForm
from ..models import (
    Client,
    Country,
    Funder,
    Project,
    ProjectPhase,
    ProjectStatus,
    ProjectTag,
    ProjectVisibility,
    VolumeUnit,
)


class ReferentialModelTests(TestCase):
    def test_country_funder_tag_unique_names(self):
        for name in ("Senegal", "World Bank", "Resilience"):
            Country.objects.create(name=name)
            Funder.objects.create(name=name)
            Client.objects.create(name=name)
            ProjectTag.objects.create(name=name)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Country.objects.create(name="Senegal")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Funder.objects.create(name="World Bank")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Client.objects.create(name="World Bank")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectTag.objects.create(name="Resilience")

    def test_country_iso3_uppercased_and_validated(self):
        country = Country(name="Benin", iso3="ben")
        country.clean()
        self.assertEqual(country.iso3, "BEN")
        country.iso3 = "blah"
        with self.assertRaises(ValidationError):
            country.clean()

    def test_referentials_ordered_by_name(self):
        Country.objects.create(name="Benin")
        Country.objects.create(name="Algeria")
        self.assertEqual(list(Country.objects.values_list("name", flat=True)), ["Algeria", "Benin"])


class ProjectT6FieldTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.country = Country.objects.create(name="Senegal")
        self.funder = Funder.objects.create(name="World Bank")
        self.tag = ProjectTag.objects.create(name="Resilience")

    def test_project_roundtrip_with_t6_fields(self):
        project = make_project(
            self.company,
            country=self.country,
            funder=self.funder,
            phase=ProjectPhase.COMPLETED,
            intervention_volume=12,
            volume_unit=VolumeUnit.PERSON_DAYS,
            personal_start=date(2024, 3, 1),
            personal_end=date(2024, 8, 30),
        )
        project.tags.add(self.tag)
        project.refresh_from_db()
        self.assertEqual(project.country.name, "Senegal")
        self.assertEqual(project.funder.name, "World Bank")
        self.assertEqual(project.get_phase_display(), "Terminé")
        self.assertEqual(project.volume_label, "12 jours-personnes")
        self.assertEqual(project.personal_period_label, "03/2024 – 08/2024")
        self.assertEqual(list(project.tags.all()), [self.tag])

    def test_volume_label_empty_without_volume(self):
        project = make_project(self.company)
        self.assertEqual(project.volume_label, "")

    def test_personal_period_label_open_ended(self):
        project = make_project(self.company, personal_start=date(2024, 3, 1))
        self.assertEqual(project.personal_period_label, "03/2024 – …")

    def test_clean_rejects_inverted_personal_dates(self):
        project = Project(
            official_name="X",
            description="x",
            deliverables="x",
            duration_start=date(2024, 1, 1),
            duration_end=date(2024, 12, 31),
            client_name="Client",
            published_by=self.company,
            personal_start=date(2024, 9, 1),
            personal_end=date(2024, 3, 1),
        )
        with self.assertRaises(ValidationError) as ctx:
            project.clean()
        self.assertIn("personal_end", ctx.exception.message_dict)

    def test_personal_dates_check_constraint(self):
        with self.assertRaises(IntegrityError):
            make_project(
                self.company,
                personal_start=date(2024, 9, 1),
                personal_end=date(2024, 3, 1),
            )

    def test_ongoing_phase_is_default(self):
        project = make_project(self.company)
        self.assertEqual(project.phase, ProjectPhase.ONGOING)


class ProjectFormT6Tests(TestCase):
    def setUp(self):
        self.company = make_company()
        Country.objects.create(name="Senegal")

    BASE = dict(
        official_name="Ziguinchor sanitation programme",
        description="Drainage and sanitation works.",
        deliverables="Diagnostics\nWorks supervision",
        duration_start="2024-01-01",
        duration_end="2025-06-30",
        budget="900000.00",
        client_name="City of Ziguinchor",
        visibility="private",
        phase="ongoing",
    )

    def test_form_creates_new_country_funder_and_tags(self):
        data = dict(
            self.BASE,
            client="City of Ziguinchor",
            country="Guinea-Bissau",
            funder="AFD",
            tags="Resilience, Sanitation",
            phase="ongoing",
            intervention_volume="8",
            volume_unit="person_months",
            personal_start="2024-02-01",
            personal_end="",
        )
        form = ProjectForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        project = form.save(commit=False)
        project.published_by = self.company
        project.status = ProjectStatus.DRAFT
        project.save()
        form.save_m2m()

        self.assertFalse(Country.objects.filter(name__iexact="guinea-bissau").count() != 1)
        project.refresh_from_db()
        self.assertEqual(project.client.name, "City of Ziguinchor")
        self.assertEqual(project.client_name, "City of Ziguinchor")
        self.assertEqual(project.country.name, "Guinea-Bissau")
        self.assertEqual(project.funder.name, "AFD")
        self.assertEqual(project.intervention_volume, 8)
        self.assertEqual(project.get_volume_unit_display(), "mois-personnes")
        tags = {t.name for t in project.tags.all()}
        self.assertEqual(tags, {"Resilience", "Sanitation"})

    def test_form_reuses_existing_referential_case_insensitively(self):
        Client.objects.create(name="City of Ziguinchor")
        data = dict(self.BASE, client="CITY OF ZIGUINCHOR", country="SENEGAL", funder="AFD")
        form = ProjectForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        project = form.save(commit=False)
        project.published_by = self.company
        project.status = ProjectStatus.DRAFT
        project.save()
        form.save_m2m()
        project.refresh_from_db()
        self.assertEqual(project.client.name, "City of Ziguinchor")
        self.assertEqual(Client.objects.count(), 1)
        self.assertEqual(project.country.name, "Senegal")
        self.assertEqual(Country.objects.count(), 1)

    def test_form_accepts_legacy_client_name_post_and_normalizes_it(self):
        data = dict(self.BASE, country="", funder="", tags="")
        form = ProjectForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        project = form.save(commit=False)
        project.published_by = self.company
        project.status = ProjectStatus.DRAFT
        project.save()
        project.refresh_from_db()
        self.assertEqual(project.client.name, "City of Ziguinchor")
        self.assertEqual(project.client_name, "City of Ziguinchor")

    def test_form_accepts_blank_referential_fields(self):
        data = dict(self.BASE, country="", funder="", tags="")
        form = ProjectForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        project = form.save(commit=False)
        project.published_by = self.company
        project.status = ProjectStatus.DRAFT
        project.save()
        self.assertIsNone(project.country)
        self.assertIsNone(project.funder)

    def test_role_list_is_extensible(self):
        from certification.models import RoleType

        expected = {
            "consultant",
            "engineer",
            "other",
            "specialist",
            "manager",
            "director",
            "assistant",
        }
        self.assertTrue(expected.issubset(set(RoleType.values)))


class ProjectListViewFilterTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.country = Country.objects.create(name="Benin")
        self.funder = Funder.objects.create(name="AFD")
        self.tag = ProjectTag.objects.create(name="Sanitation")
        self.benin = make_project(
            self.company,
            official_name="Cotonou drains",
            status=ProjectStatus.PUBLISHED,
            visibility=ProjectVisibility.PUBLIC,
            client=Client.objects.create(name="Ministry of Water"),
            country=self.country,
            funder=self.funder,
            phase=ProjectPhase.COMPLETED,
        )
        self.benin.tags.add(self.tag)
        self.senegal = make_project(
            self.company,
            official_name="Dakar mobility",
            status=ProjectStatus.PUBLISHED,
            visibility=ProjectVisibility.PUBLIC,
        )

    def test_filter_by_country(self):
        response = self.client.get(reverse("projects:list"), {"country": "Benin"})
        self.assertContains(response, "Cotonou drains")
        self.assertNotContains(response, "Dakar mobility")

    def test_filter_by_client(self):
        response = self.client.get(reverse("projects:list"), {"client": "Ministry of Water"})
        self.assertContains(response, "Cotonou drains")
        self.assertNotContains(response, "Dakar mobility")

    def test_filter_by_funder(self):
        response = self.client.get(reverse("projects:list"), {"funder": "AFD"})
        self.assertContains(response, "Cotonou drains")
        self.assertNotContains(response, "Dakar mobility")

    def test_filter_by_phase(self):
        response = self.client.get(reverse("projects:list"), {"phase": "completed"})
        self.assertContains(response, "Cotonou drains")
        self.assertNotContains(response, "Dakar mobility")

    def test_filter_by_tag(self):
        response = self.client.get(reverse("projects:list"), {"tag": "Sanitation"})
        self.assertContains(response, "Cotonou drains")
        self.assertNotContains(response, "Dakar mobility")

    def test_search_covers_country_client_and_funder(self):
        response = self.client.get(reverse("projects:list"), {"q": "Ministry of Water"})
        self.assertContains(response, "Cotonou drains")
        self.assertNotContains(response, "Dakar mobility")

        response = self.client.get(reverse("projects:list"), {"q": "AFD"})
        self.assertContains(response, "Cotonou drains")
        self.assertNotContains(response, "Dakar mobility")


class ProjectCreateT6ViewTests(TestCase):
    def test_create_persists_t6_fields_and_redirects(self):
        self.client.force_login(make_company())
        response = self.client.post(
            reverse("projects:create"),
            {
                "official_name": "Ouakam coastal defence",
                "description": "Shore protection works.",
                "deliverables": "Design\nSupervision",
                "duration_start": "2024-02-01",
                "duration_end": "2025-01-31",
                "budget": "1500000.00",
                "client_name": "City of Dakar",
                "client": "City of Dakar",
                "visibility": "private",
                "country": "Senegal",
                "funder": "World Bank",
                "phase": "ongoing",
                "intervention_volume": "10",
                "volume_unit": "person_months",
                "personal_start": "2024-03-01",
                "personal_end": "",
                "tags": "Resilience, Coastal",
            },
        )
        project = Project.objects.get(official_name="Ouakam coastal defence")
        self.assertTrue(response.status_code in (200, 302))
        self.assertEqual(project.country.name, "Senegal")
        self.assertEqual(project.client.name, "City of Dakar")
        self.assertEqual(project.funder.name, "World Bank")
        self.assertEqual(project.personal_period_label, "03/2024 – …")
        self.assertEqual({t.name for t in project.tags.all()}, {"Resilience", "Coastal"})
