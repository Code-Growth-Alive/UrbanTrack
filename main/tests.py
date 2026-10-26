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
        self.assertContains(response, "Cette page n'existe pas.", status_code=404)

    def test_403_page_renders_custom_template(self):
        from main.views import handler403

        response = handler403(self.request)
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Vous n'avez pas accès à cette page.", status_code=403)

    def test_400_page_renders_custom_template(self):
        from main.views import handler400

        response = handler400(self.request)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "La requête n'a pas pu être comprise.", status_code=400)

    def test_500_page_renders_custom_template(self):
        from main.views import handler500

        response = handler500(self.request)
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, "Une erreur est survenue de notre côté.", status_code=500)


class RequestLoggingTests(TestCase):
    def test_request_is_logged_with_correlation_id(self):
        with self.assertLogs("urbantrack.requests", level="INFO") as captured:
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        request_id = response["X-Request-ID"]
        self.assertEqual(len(request_id), 32)
        self.assertEqual(captured.records[0].request_id, request_id)
        self.assertEqual(captured.records[0].status_code, 200)
        self.assertIn("status=200", captured.records[0].getMessage())

    def test_incoming_request_id_is_reused(self):
        response = self.client.get("/", headers={"X-Request-ID": "client-request-123"})

        self.assertEqual(response["X-Request-ID"], "client-request-123")

    def test_invalid_incoming_request_id_is_replaced(self):
        response = self.client.get("/", headers={"X-Request-ID": "bad value with spaces"})

        self.assertNotEqual(response["X-Request-ID"], "bad value with spaces")
        self.assertEqual(len(response["X-Request-ID"]), 32)

    def test_static_paths_are_not_logged(self):
        with self.assertNoLogs("urbantrack.requests", level="INFO"):
            self.client.get("/static/missing.css")


class JsonLogFormatterTests(TestCase):
    def test_json_payload_contains_structured_fields(self):
        import json
        import logging

        from main.logging import JsonFormatter

        record = logging.LogRecord(
            name="urbantrack.audit",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="event=%s",
            args=("projects.published",),
            exc_info=None,
        )
        record.request_id = "abc123"
        record.event = "projects.published"
        record.fields = {"project_id": 42, "actor_id": 7}

        payload = json.loads(JsonFormatter().format(record))

        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["request_id"], "abc123")
        self.assertEqual(payload["event"], "projects.published")
        self.assertEqual(payload["project_id"], 42)
        self.assertEqual(payload["actor_id"], 7)
