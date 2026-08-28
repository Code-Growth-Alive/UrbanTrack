"""Tests for the custom error page handlers and templates."""

from django.test import RequestFactory, TestCase


class ErrorPageTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.get("/")

    def test_404_page_renders_custom_template(self):
        from django.test import Client
        from django.test.utils import override_settings

        with override_settings(ALLOWED_HOSTS=["testserver"]):
            response = Client().get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "404", status_code=404)
        self.assertContains(response, "This page doesn't exist", status_code=404)

    def test_403_page_renders_custom_template(self):
        from urbantrack.views import handler403

        response = handler403(self.request)
        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response, "You don't have access to this page", status_code=403
        )

    def test_400_page_renders_custom_template(self):
        from urbantrack.views import handler400

        response = handler400(self.request)
        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response, "The request could not be understood", status_code=400
        )

    def test_500_page_renders_custom_template(self):
        from urbantrack.views import handler500

        response = handler500(self.request)
        self.assertEqual(response.status_code, 500)
        self.assertContains(
            response, "Something went wrong on our side.", status_code=500
        )
