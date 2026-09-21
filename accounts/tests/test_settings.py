"""Tests for account settings: profile picture, personal details, password change."""

import io
import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


def make_expert(email="settings@example.com", **overrides):
    defaults = dict(
        username=email,
        email=email,
        password="S3cret!pass",
        role="user",
        email_confirmed=True,
        first_name="Settings",
        last_name="User",
    )
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def make_png():
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color=(16, 32, 48)).save(buffer, format="PNG")
    return buffer.getvalue()


class AccountSettingsTests(TestCase):
    def setUp(self):
        self.user = make_expert()
        self.client.force_login(self.user)

    def test_settings_page_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:settings"))
        self.assertEqual(response.status_code, 302)

    def test_settings_renders_for_authenticated_user(self):
        response = self.client.get(reverse("accounts:settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Paramètres du compte")

    def test_can_update_personal_details(self):
        response = self.client.post(
            reverse("accounts:settings"),
            {"first_name": "Aminata", "last_name": "Sow"},
        )
        self.assertRedirects(response, reverse("accounts:settings"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Aminata")
        self.assertEqual(self.user.last_name, "Sow")

    def test_can_upload_profile_picture(self):
        avatar = SimpleUploadedFile("me.png", make_png(), content_type="image/png")
        response = self.client.post(
            reverse("accounts:settings"),
            {
                "first_name": self.user.first_name,
                "last_name": self.user.last_name,
                "avatar": avatar,
            },
        )
        self.assertRedirects(response, reverse("accounts:settings"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar)
        self.assertTrue(self.user.avatar.name.startswith("avatars/"))

    def test_password_change_updates_credentials(self):
        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "S3cret!pass",
                "new_password1": "N3w.S3cret!pass",
                "new_password2": "N3w.S3cret!pass",
            },
        )
        self.assertRedirects(response, reverse("accounts:settings"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("N3w.S3cret!pass"))

    def test_password_change_rejects_wrong_old_password(self):
        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "wrong",
                "new_password1": "N3w.S3cret!pass",
                "new_password2": "N3w.S3cret!pass",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("S3cret!pass"))

    def test_avatar_shown_on_public_profile(self):
        self.user.avatar = SimpleUploadedFile("me.png", make_png(), content_type="image/png")
        self.user.save()
        response = self.client.get(
            reverse("accounts:public_profile", args=[self.user.professional_id])
        )
        self.assertContains(response, self.user.avatar.url)


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = make_expert()

    def test_reset_page_renders(self):
        response = self.client.get(reverse("accounts:password_reset"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Réinitialiser votre mot de passe")

    def test_reset_emails_link_and_works_with_user(self):
        mail.outbox = []
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "settings@example.com"},
        )
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        match = re.search(r"/reset/([\w-]+)/([\w-]+)/", body)
        self.assertIsNotNone(match, "Reset link missing from email")
        uidb64, token = match.groups()
        # Clicking the link stores the token and redirects to a token-less URL.
        response = self.client.get(reverse("accounts:password_reset_confirm", args=[uidb64, token]))
        self.assertEqual(response.status_code, 302)
        set_url = response["Location"]
        self.assertTrue(set_url.endswith("/set-password/"))
        response = self.client.post(
            set_url,
            {"new_password1": "R3set!pass", "new_password2": "R3set!pass"},
        )
        self.assertRedirects(response, reverse("accounts:password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("R3set!pass"))

    def test_accepts_username_instead_of_email(self):
        self.user.username = "legacy-handle"
        self.user.save()
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "legacy-handle"},
        )
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)

    def test_unknown_identity_does_not_leak_accounts(self):
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "nobody@example.com"},
        )
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_token_shows_invalid_link_page(self):
        response = self.client.get(
            reverse("accounts:password_reset_confirm", args=["bad-uid", "bad-token"])
        )
        self.assertEqual(response.status_code, 200)
