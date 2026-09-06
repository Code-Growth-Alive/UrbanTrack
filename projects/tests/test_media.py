"""Project media & link tests (optional attachments on projects)."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from projects.models import Project, ProjectLink, ProjectMedia, ProjectVisibility
from projects.services import publish_project


def make_company():
    from accounts.models import Company as CompanyModel

    company = CompanyModel.objects.create(name="Media Corp")
    return User.objects.create_user(
        username="media.corp",
        email="media@corp.com",
        password="S3cret!pass",
        role=Role.USER,
        company=company,
        email_confirmed=True,
        first_name="Fatou",
        last_name="Ndiaye",
    )


class ManageMediaTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.project = Project.objects.create(
            official_name="Media project",
            description="d",
            deliverables="a\nb",
            duration_start="2025-01-01",
            budget=1000,
            client_name="Client",
            visibility=ProjectVisibility.PUBLIC,
            published_by=self.company,
        )
        publish_project(self.project)
        self.url = reverse("projects:manage", args=[self.project.pk])
        self.client.force_login(self.company)

    def test_add_and_remove_link(self):
        response = self.client.post(
            self.url,
            {
                "action": "add_link",
                "label": "Appraisal report",
                "url": "https://example.org/report",
            },
        )
        self.assertRedirects(response, self.url)
        self.assertEqual(ProjectLink.objects.count(), 1)
        link = ProjectLink.objects.get()
        response = self.client.post(self.url, {"action": "delete_link", "link_pk": link.pk})
        self.assertEqual(ProjectLink.objects.count(), 0)

    def test_add_document_and_public_display(self):
        upload = SimpleUploadedFile("report.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        response = self.client.post(
            self.url,
            {
                "action": "add_media",
                "kind": "document",
                "caption": "Final report",
                "file": upload,
            },
        )
        self.assertRedirects(response, self.url)
        item = ProjectMedia.objects.get()
        self.assertEqual(item.kind, "document")
        self.assertTrue(item.file)

        detail = self.client.get(reverse("projects:detail", args=[self.project.pk]))
        self.assertContains(detail, "Final report")
        self.assertContains(detail, item.file.url)

    def test_image_without_file_rejected(self):
        self.client.post(
            self.url,
            {"action": "add_media", "kind": "image", "caption": ""},
        )
        self.assertEqual(ProjectMedia.objects.count(), 0)
