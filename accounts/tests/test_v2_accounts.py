"""
HTTP tests for the v2 account model:

* case-insensitive company create-or-join on signup,
* two roles only (user/admin), superuser-only admin nomination,
* email confirmation: 6-digit code, 24h expiry, resend, change-email
  re-confirmation, deletion of unconfirmed accounts.
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.email_confirmation import confirm_email, purge_expired_unconfirmed
from accounts.models import Company, ExpertProfile, Role, User

SIGNUP_PAYLOAD = {
    "first_name": "Aminata",
    "last_name": "Sow",
    "email": "aminata@example.com",
    "password1": "S3cret!pass",
    "password2": "S3cret!pass",
}


def make_user(email="corp@example.com", **overrides):
    defaults = dict(
        username=email,
        email=email,
        email_confirmed=True,
    )
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


class SignUpCompanyTests(TestCase):
    def test_signup_creates_company_and_redirects_to_confirmation(self):
        payload = dict(SIGNUP_PAYLOAD, company_name="Ministry of Urban Renewal")
        response = self.client.post(reverse("accounts:signup"), payload)
        self.assertRedirects(response, reverse("accounts:confirm_email"))

        user = User.objects.get(email="aminata@example.com")
        self.assertEqual(user.role, Role.USER)
        self.assertEqual(user.company.name, "Ministry of Urban Renewal")
        self.assertEqual(user.email_confirmed, False)
        self.assertEqual(len(user.confirmation_code), 6)
        self.assertTrue(user.confirmation_code.isdigit())
        self.assertTrue(ExpertProfile.objects.filter(user=user).exists())
        # Logged in, but the confirmation page is the landing spot.
        self.assertIn("_auth_user_id", self.client.session)

    def test_signup_joins_existing_company_case_insensitively(self):
        Company.objects.create(name="Suez Africa")
        payload = dict(SIGNUP_PAYLOAD, email="b@example.com", company_name="suez africa")
        self.client.post(reverse("accounts:signup"), payload)
        self.assertEqual(Company.objects.count(), 1)
        user = User.objects.get(email="b@example.com")
        self.assertEqual(user.company.name, "Suez Africa")

    def test_signup_without_company_is_allowed(self):
        self.client.post(reverse("accounts:signup"), SIGNUP_PAYLOAD)
        user = User.objects.get(email="aminata@example.com")
        self.assertIsNone(user.company)

    def test_duplicate_email_still_rejected(self):
        make_user(email="aminata@example.com")
        response = self.client.post(reverse("accounts:signup"), SIGNUP_PAYLOAD)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(email="aminata@example.com").count(), 1)

    def test_no_role_picker_on_signup_page(self):
        response = self.client.get(reverse("accounts:signup"))
        self.assertNotContains(response, 'name="role"')


class ConfirmEmailTests(TestCase):
    def setUp(self):
        self.client.post(reverse("accounts:signup"), SIGNUP_PAYLOAD)
        self.user = User.objects.get(email="aminata@example.com")

    def test_wrong_code_rejected(self):
        response = self.client.post(reverse("accounts:confirm_email"), {"code": "000000"})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_confirmed)

    def test_correct_code_confirms_and_reaches_dashboard(self):
        response = self.client.post(
            reverse("accounts:confirm_email"), {"code": self.user.confirmation_code}
        )
        self.assertRedirects(response, reverse("accounts:dashboard"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_confirmed)
        # The code is consumed.
        self.assertEqual(self.user.confirmation_code, "")

    def test_confirmed_users_skip_confirmation_page(self):
        confirm_email(self.user, self.user.confirmation_code)
        response = self.client.get(reverse("accounts:confirm_email"))
        self.assertRedirects(response, reverse("accounts:dashboard"))

    def test_unconfirmed_users_are_gated_from_dashboard(self):
        # Fresh signup (unconfirmed) hitting the dashboard bounces to confirm.
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertRedirects(response, reverse("accounts:confirm_email"))

    def test_resend_issues_a_fresh_code(self):
        old = self.user.confirmation_code
        response = self.client.post(reverse("accounts:resend_confirmation_code"))
        self.assertRedirects(response, reverse("accounts:confirm_email"))
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.confirmation_code, old)


class ConfirmationExpiryTests(TestCase):
    def test_expired_code_rejected(self):
        payload = dict(SIGNUP_PAYLOAD, email="x@example.com")
        self.client.post(reverse("accounts:signup"), payload)
        user = User.objects.get(email="x@example.com")
        user.confirmation_code_created_at = timezone.now() - timedelta(hours=25)
        user.save(update_fields=["confirmation_code_created_at"])
        with self.assertRaises(Exception):
            confirm_email(user, user.confirmation_code)

    def test_purge_deletes_expired_unconfirmed_only(self):
        expired = make_user(
            email="expired@example.com",
            email_confirmed=False,
            username="expired@example.com",
        )
        expired.confirmation_code = "123456"
        expired.confirmation_code_created_at = timezone.now() - timedelta(hours=25)
        expired.save()

        confirmed = make_user(email="ok@example.com")
        fresh = make_user(
            email="fresh@example.com",
            email_confirmed=False,
            username="fresh@example.com",
        )
        fresh.confirmation_code = "123456"
        fresh.confirmation_code_created_at = timezone.now()
        fresh.save()

        deleted = purge_expired_unconfirmed()
        self.assertEqual(deleted, 1)
        self.assertFalse(User.objects.filter(pk=expired.pk).exists())
        self.assertTrue(User.objects.filter(pk=confirmed.pk).exists())
        self.assertTrue(User.objects.filter(pk=fresh.pk).exists())


class NominationTests(TestCase):
    def _post_signup(self, email):
        payload = dict(SIGNUP_PAYLOAD, email=email)
        self.client.post(reverse("accounts:signup"), payload)
        user = User.objects.get(email=email)
        confirm_email(user, user.confirmation_code)
        return user

    def test_superuser_can_nominate_an_admin(self):
        superuser = User.objects.create_superuser(
            username="root", email="root@example.com", password="S3cret!pass"
        )
        target = self._post_signup("target@example.com")
        self.assertEqual(target.role, Role.USER)

        self.client.force_login(superuser)
        response = self.client.post(
            reverse("adminpanel:user_nominate_admin", args=[target.pk]),
            {"make_admin": "1"},
        )
        self.assertRedirects(response, reverse("adminpanel:user_list"))
        target.refresh_from_db()
        self.assertEqual(target.role, Role.ADMIN)
        self.assertTrue(target.is_system_admin)

    def test_admin_cannot_nominate_another_admin(self):
        admin = self._post_signup("admin@example.com")
        admin.role = Role.ADMIN
        admin.save(update_fields=["role"])
        # Sign the admin out before creating the target account.
        self.client.post(reverse("accounts:logout"))
        target = self._post_signup("target2@example.com")

        self.client.force_login(admin)
        self.client.post(
            reverse("adminpanel:user_nominate_admin", args=[target.pk]),
            {"make_admin": "1"},
        )
        # Superuser-only action -> the request is not processed.
        target.refresh_from_db()
        self.assertEqual(target.role, Role.USER)


class EmailChangeTests(TestCase):
    def test_email_change_requires_reconfirmation(self):
        self._post_signup = None
        self.client.post(reverse("accounts:signup"), SIGNUP_PAYLOAD)
        user = User.objects.get(email="aminata@example.com")
        confirm_email(user, user.confirmation_code)

        response = self.client.post(reverse("accounts:change_email"), {"email": "new@example.com"})
        self.assertRedirects(response, reverse("accounts:confirm_email"))
        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")
        self.assertFalse(user.email_confirmed)
        self.assertEqual(len(user.confirmation_code), 6)


class RoleModelTests(TestCase):
    def test_default_role_is_user(self):
        user = make_user()
        self.assertEqual(user.role, Role.USER)
        self.assertTrue(user.is_expert)
        self.assertFalse(user.is_admin_role)

    def test_admin_role_grants_system_admin(self):
        user = make_user()
        user.role = Role.ADMIN
        self.assertTrue(user.is_system_admin)
        self.assertTrue(user.is_admin_role)
        self.assertFalse(user.is_company)
        self.assertFalse(user.is_donor)

    def test_organisation_name_mirrors_company(self):
        company = Company.objects.create(name="World Bank")
        user = make_user(company=company)
        self.assertEqual(user.organisation_name, "World Bank")
        user.company = None
        user.save(update_fields=["company"])
        self.assertEqual(user.organisation_name, "")


class DirectoryTests(TestCase):
    def test_only_confirmed_users_appear_in_directory(self):
        make_user(email="in@example.com")
        unconfirmed = make_user(
            email="out@example.com", username="out@example.com", email_confirmed=False
        )
        unconfirmed.confirmation_code = "111111"
        unconfirmed.confirmation_code_created_at = timezone.now()
        unconfirmed.save()

        response = self.client.get(reverse("accounts:expert_list"))
        self.assertContains(response, "in@example.com")
        self.assertNotContains(response, "out@example.com")

    def test_expert_search_hides_unconfirmed(self):
        make_user(email="in@example.com")
        self.client.force_login(make_user(email="searcher@example.com"))
        payload = self.client.get(reverse("accounts:expert_search"), {"q": "in@"}).json()
        emails = [row["email"] for row in payload["results"]]
        self.assertIn("in@example.com", emails)
        self.assertNotIn("out@example.com", emails)
