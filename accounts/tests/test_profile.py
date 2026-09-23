"""Tests for ExpertProfile: portfolio, cv_template reservation, trust score."""

from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from ..models import (
    Company,
    CvTemplate,
    ExpertProfile,
    Mandate,
    MediaAppearance,
    Position,
    Publication,
    Role,
    Skill,
    TeachingEntry,
    Training,
)

User = get_user_model()


def make_expert(username="pro", email=None):
    return User.objects.create_user(
        username=username,
        email=email or f"{username}@example.com",
        first_name="Pro",
        last_name="File",
    )


class ExpertProfileSignalTests(TestCase):
    def test_profile_auto_created_for_experts(self):
        expert = make_expert()
        profile = ExpertProfile.objects.get(user=expert)
        self.assertEqual(profile.cv_template, CvTemplate.WORLD_BANK)

    def test_profile_created_for_all_users(self):
        user = User.objects.create_user(username="late", email="late@example.com", role=Role.USER)
        user.role = Role.ADMIN
        user.save()
        self.assertTrue(ExpertProfile.objects.filter(user=user).exists())


class PortfolioTests(TestCase):
    def setUp(self):
        self.expert = make_expert()
        self.profile = self.expert.expert_profile

    def test_skill_tags_deduplicated(self):
        Skill.objects.create(name="Urban planning")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Skill.objects.create(name="Urban planning")
        skill = Skill.objects.get(name="Urban planning")
        self.profile.skills.add(skill)
        self.assertIn(skill, self.profile.skills.all())

    def test_trainings_ordered_recent_first(self):
        Training.objects.create(profile=self.profile, title="Old cert", institution="X", year=2010)
        Training.objects.create(profile=self.profile, title="New cert", institution="Y", year=2023)
        titles = list(self.profile.trainings.values_list("title", flat=True))
        self.assertEqual(titles, ["New cert", "Old cert"])

    def test_cv_template_choices_cover_all_skins(self):
        self.assertEqual(
            set(CvTemplate.values),
            {"afd", "world_bank_new"},
        )

    def test_absolute_url_uses_permanent_oxid(self):
        url = self.profile.get_absolute_url()
        self.assertIn(self.expert.professional_id, url)
        self.assertTrue(url.startswith("/experts/"))

    def test_trust_score_methodology_page_is_public(self):
        response = self.client.get(reverse("accounts:trust_score"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Score de confiance")
        self.assertContains(response, "contributions certifiées")

    def test_public_company_page_renders_and_exposes_seo_tags(self):
        company = Company.objects.create(
            name="Urban Studio",
            country="Senegal",
            founded_year=2010,
            size="11-50",
            domains=["Urban planning", "Transport"],
            accreditations=["Bureau agréé"],
            description="A public profile for the company.",
        )
        response = self.client.get(reverse("accounts:company_public", args=[company.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Urban Studio")
        self.assertContains(response, 'property="og:title"')
        self.assertContains(response, 'name="twitter:card"')


class DeclaredSectionsModelTests(TestCase):
    """T4/T4a: positions, mandates, publications, teaching, media, JSON blocks."""

    def setUp(self):
        self.profile = make_expert().expert_profile

    def test_extended_profile_fields_round_trip(self):
        self.profile.nationality = "Senegalese"
        self.profile.phone = "+221 77 000 00 00"
        self.profile.birth_date = date(1980, 5, 1)
        self.profile.strengths = ["Donor relations", "GIS"]
        self.profile.countries_of_intervention = ["Senegal", "Benin"]
        self.profile.languages = [
            {"name": "French", "read": "fluent", "spoken": "native", "written": "fluent"}
        ]
        self.profile.misc = "Member, Ordre des architectes"
        self.profile.save()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.nationality, "Senegalese")
        self.assertEqual(self.profile.phone, "+221 77 000 00 00")
        self.assertEqual(self.profile.birth_date, date(1980, 5, 1))
        self.assertEqual(self.profile.strengths, ["Donor relations", "GIS"])
        self.assertEqual(self.profile.countries_of_intervention, ["Senegal", "Benin"])
        self.assertEqual(self.profile.languages[0]["read"], "fluent")
        self.assertEqual(self.profile.misc, "Member, Ordre des architectes")

    def test_positions_ordered_newest_first_with_open_end(self):
        Position.objects.create(
            profile=self.profile,
            employer="ACME",
            function="Consultant",
            date_start=date(2015, 1, 1),
            date_end=date(2017, 12, 31),
        )
        Position.objects.create(
            profile=self.profile,
            employer="IRD",
            function="Director of studies",
            date_start=date(2018, 1, 1),
        )
        positions = list(self.profile.positions.all())
        self.assertEqual([p.function for p in positions], ["Director of studies", "Consultant"])
        self.assertIsNone(positions[0].date_end)

    def test_mandate_publication_teaching_media_creation(self):
        Mandate.objects.create(
            profile=self.profile, name="OAI", role="Board member", year_start=2021
        )
        Publication.objects.create(profile=self.profile, title="Villes secondaires", year=2022)
        TeachingEntry.objects.create(profile=self.profile, title="Urban economics", year=2019)
        MediaAppearance.objects.create(profile=self.profile, title="RFI interview", year=2021)
        self.assertEqual(self.profile.mandates.count(), 1)
        self.assertEqual(self.profile.publications.count(), 1)
        self.assertEqual(self.profile.teaching_entries.count(), 1)
        self.assertEqual(self.profile.media_appearances.count(), 1)

    def test_empty_profile_defaults_are_empty_lists(self):
        self.assertEqual(self.profile.strengths, [])
        self.assertEqual(self.profile.languages, [])
