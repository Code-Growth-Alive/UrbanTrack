"""Tests for the custom User model and the permanent professional ID."""

import re

from django.db.utils import IntegrityError
from django.test import TestCase

from ..models import Role, User
from ..utils import generate_professional_id

PROFESSIONAL_ID_RE = re.compile(r"^OX-[A-HJ-NP-Z2-9]{6}$")


class ProfessionalIdGenerationTests(TestCase):
    def test_generated_id_matches_format(self):
        self.assertRegex(generate_professional_id(), PROFESSIONAL_ID_RE)

    def test_no_ambiguous_characters(self):
        for _ in range(200):
            candidate = generate_professional_id()
            for forbidden in ("I", "O", "0", "1"):
                self.assertNotIn(forbidden, candidate.split("-")[1])


class UserModelTests(TestCase):
    def test_default_role_is_expert(self):
        user = User.objects.create_user(username="ama", email="ama@example.com")
        self.assertEqual(user.role, Role.EXPERT)

    def test_all_three_roles_available(self):
        self.assertEqual(
            set(Role.values), {"expert", "company", "donor"}
        )

    def test_professional_id_assigned_on_creation(self):
        user = User.objects.create_user(username="kwame", email="kwame@example.com")
        self.assertRegex(user.professional_id, PROFESSIONAL_ID_RE)

    def test_professional_id_unique_across_users(self):
        ids = [
            User.objects.create_user(
                username=f"user{i}", email=f"user{i}@example.com"
            ).professional_id
            for i in range(50)
        ]
        self.assertEqual(len(ids), len(set(ids)))

    def test_professional_id_permanent_after_edit(self):
        """The professional ID never changes once assigned (Epic -1 rule)."""
        user = User.objects.create_user(username="zola", email="zola@example.com")
        original = user.professional_id
        user.first_name = "Zola"
        user.save()
        user.refresh_from_db()
        self.assertEqual(user.professional_id, original)

    def test_explicitly_set_professional_id_is_respected(self):
        user = User.objects.create_user(
            username="fixed",
            email="fixed@example.com",
            professional_id="OX-AAA234",
        )
        user.refresh_from_db()
        self.assertEqual(user.professional_id, "OX-AAA234")

    def test_email_must_be_unique(self):
        User.objects.create_user(username="a", email="dup@example.com")
        with self.assertRaises(IntegrityError):
            User.objects.create_user(username="b", email="dup@example.com")

    def test_email_domain_normalised(self):
        user = User.objects.create_user(
            username="n", email="someone@EXAMPLE.COM"
        )
        self.assertEqual(user.email, "someone@example.com")

    def test_role_helpers(self):
        company = User.objects.create_user(
            username="corp",
            email="corp@example.com",
            role=Role.COMPANY,
            organisation_name="BTP & Co",
        )
        donor = User.objects.create_user(
            username="wb",
            email="wb@example.com",
            role=Role.DONOR,
            organisation_name="World Bank",
        )
        self.assertTrue(company.is_company)
        self.assertTrue(donor.is_donor)
        self.assertFalse(company.is_expert)

    def test_str_includes_professional_id(self):
        user = User.objects.create_user(
            username="ida", email="ida@example.com", first_name="Ida"
        )
        self.assertIn(user.professional_id, str(user))
