"""Tests for account settings: profile picture, personal details, password change."""

import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


def make_expert(email="settings@example.com", **overrides):
    defaults = dict(
        username=email,
        email=email,
        password="S3cret!pass",
        role="expert",
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
        self.assertContains(response, "Account settings")

    def test_can_update_personal_details(self):
        response = self.client.post(
            reverse("accounts:settings"),
            {"first_name": "Aminata", "last_name": "Sow", "organisation_name": ""},
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
                "organisation_name": "",
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
        self.user.avatar = SimpleUploadedFile(
            "me.png", make_png(), content_type="image/png"
        )
        self.user.save()
        response = self.client.get(
            reverse("accounts:public_profile", args=[self.user.professional_id])
        )
        self.assertContains(response, self.user.avatar.url)
