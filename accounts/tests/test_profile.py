"""Tests for ExpertProfile: portfolio, cv_template reservation, trust score."""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from ..models import CvTemplate, ExpertProfile, Role, Skill, Training

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
        self.assertEqual(profile.cv_template, CvTemplate.ACADEMIC_HARVARD_MIT)

    def test_companies_and_donors_have_no_profile(self):
        company = User.objects.create_user(
            username="corp", email="corp@example.com", role=Role.COMPANY
        )
        donor = User.objects.create_user(
            username="donor", email="donor@example.org", role=Role.DONOR
        )
        self.assertFalse(ExpertProfile.objects.filter(user=company).exists())
        self.assertFalse(ExpertProfile.objects.filter(user=donor).exists())

    def test_role_change_creates_profile(self):
        user = User.objects.create_user(
            username="late", email="late@example.com", role=Role.COMPANY
        )
        user.role = Role.EXPERT
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

    def test_cv_template_choices_cover_all_three_skins(self):
        self.assertEqual(
            set(CvTemplate.values),
            {"academic_harvard_mit", "afd", "world_bank"},
        )

    def test_absolute_url_uses_permanent_oxid(self):
        url = self.profile.get_absolute_url()
        self.assertIn(self.expert.professional_id, url)
        self.assertTrue(url.startswith("/experts/"))
