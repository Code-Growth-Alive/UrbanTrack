"""
HTTP tests of the project publishing flow (Epic 2): directory, creation,
contributor declaration, publish/archive and adjustment validation.
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from projects.tests.test_models import make_company, make_project

from ..models import Project, ProjectStatus, ProjectVisibility

User = get_user_model()

PROJECT_DATA = {
    "official_name": "Coastal protection works, Lomé",
    "description": "Shoreline protection and drainage rehabilitation.",
    "deliverables": "Feasibility study\nWorks supervision",
    "duration_start": "2024-03-01",
    "duration_end": "2025-09-30",
    "budget": "1800000.00",
    "client_name": "Ministry of Public Works",
    "visibility": "private",
}


class ProjectDirectoryTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.public_project = make_project(
            self.company,
            official_name="Public project",
            status=ProjectStatus.PUBLISHED,
            visibility=ProjectVisibility.PUBLIC,
        )
        self.draft_project = make_project(self.company, official_name="Draft project")
        self.private_published = make_project(
            self.company,
            official_name="Private project",
            status=ProjectStatus.PUBLISHED,
        )

    def test_list_shows_only_published_public_projects(self):
        response = self.client.get(reverse("projects:list"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Public project", content)
        self.assertNotIn("Draft project", content)
        self.assertNotIn("Private project", content)

    def test_archived_project_leaves_directory_and_detail(self):
        from projects.services import archive_project

        archive_project(self.public_project)
        self.assertNotContains(self.client.get(reverse("projects:list")), "Public project")
        response = self.client.get(reverse("projects:detail", args=[self.public_project.pk]))
        self.assertEqual(response.status_code, 404)


class ProjectCreateTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.expert = User.objects.create_user(
            username="exp",
            email="exp@example.com",
            password="S3cret!pass",
            role="expert",
        )
        self.url = reverse("projects:create")

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_experts_cannot_publish(self):
        self.client.force_login(self.expert)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_company_creates_draft_and_lands_on_manage(self):
        self.client.force_login(self.company)
        response = self.client.post(self.url, PROJECT_DATA)
        self.assertEqual(response.status_code, 302)
        project = Project.objects.get(official_name=PROJECT_DATA["official_name"])
        self.assertEqual(project.status, ProjectStatus.DRAFT)
        self.assertEqual(project.published_by, self.company)
        self.assertRedirects(response, reverse("projects:manage", args=[project.pk]))


class ProjectManageTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.other_company = make_company(username="other", email="other@corp.com")
        self.project = make_project(self.company)
        self.url = reverse("projects:manage", args=[self.project.pk])
        self.expert = User.objects.create_user(
            username="bintou",
            email="bintou@example.com",
            password="S3cret!pass",
            role="expert",
            first_name="Bintou",
            last_name="Traore",
        )

    def test_owner_required(self):
        self.client.force_login(self.other_company)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_declare_contributor_on_draft(self):
        self.client.force_login(self.company)
        response = self.client.post(
            self.url,
            {
                "action": "declare",
                "email": "bintou@example.com",
                "role_type": "manager",
                "contribution_bullets": "Managed site works",
            },
        )
        self.assertEqual(response.status_code, 302)
        contribution = self.project.contributions.get()
        self.assertEqual(contribution.expert, self.expert)
        self.assertEqual(len(mail.outbox), 0)  # silent until publish

    def test_declare_by_unknown_email_then_publish_dispatches_invitation(self):
        self.client.force_login(self.company)
        self.client.post(
            self.url,
            {
                "action": "declare",
                "email": "unknown@example.com",
                "role_type": "specialist",
                "contribution_bullets": "GIS analysis",
            },
        )
        self.client.post(self.url, {"action": "publish"})
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.PUBLISHED)
        self.assertEqual(len(mail.outbox), 1)
        invitation = self.project.contributions.get().invitations.get()
        self.assertIn(str(invitation.token), mail.outbox[0].body)

    def test_invalid_declare_form_preserves_errors(self):
        self.client.force_login(self.company)
        response = self.client.post(
            self.url,
            {"action": "declare", "email": "not-an-email", "role_type": "manager"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid email address")

    def test_visibility_only_while_draft(self):
        self.client.force_login(self.company)
        self.client.post(self.url, {"action": "visibility", "visibility": "public"})
        self.project.refresh_from_db()
        self.assertEqual(self.project.visibility, ProjectVisibility.PUBLIC)

        self.client.post(self.url, {"action": "publish"})
        self.client.post(self.url, {"action": "visibility", "visibility": "private"})
        self.project.refresh_from_db()
        # Published projects keep their visibility; no crash either way.
        self.assertEqual(self.project.visibility, ProjectVisibility.PUBLIC)

    def test_archive_from_manage(self):
        self.client.force_login(self.company)
        self.client.post(self.url, {"action": "publish"})
        response = self.client.post(self.url, {"action": "archive"})
        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.ARCHIVED)


class CertificationSurfacingTests(TestCase):
    """Epic 4: confirmed work appears on profile and project pages."""

    def test_certified_contribution_links_both_pages(self):
        from certification.services import confirm_as_is, declare_contributor

        company = make_company()
        expert = User.objects.create_user(
            username="awa",
            email="awa@example.com",
            password="S3cret!pass",
            role="expert",
            first_name="Awa",
            last_name="Diop",
        )
        project = make_project(
            company,
            status=ProjectStatus.PUBLISHED,
            visibility=ProjectVisibility.PUBLIC,
        )
        contribution = declare_contributor(
            project,
            email="awa@example.com",
            role_type="director",
            contribution_bullets="Led the design",
            added_by=company,
        )
        confirm_as_is(contribution, expert)

        profile = self.client.get(reverse("accounts:public_profile", args=[expert.professional_id]))
        detail = self.client.get(reverse("projects:detail", args=[project.pk]))
        self.assertContains(profile, project.official_name)
        self.assertContains(detail, "Awa Diop")
        self.assertContains(profile, "Trust score")


class ProjectCrudTests(TestCase):
    """Owner is able to edit and delete their own projects."""

    def setUp(self):
        self.company = make_company()
        self.project = make_project(self.company)

    def test_owner_can_edit_project_fields(self):
        self.client.force_login(self.company)
        data = dict(PROJECT_DATA)
        data["official_name"] = "Renamed coastal rebuild"
        response = self.client.post(
            reverse("projects:edit", args=[self.project.pk]), data
        )
        self.assertRedirects(response, reverse("projects:manage", args=[self.project.pk]))
        self.project.refresh_from_db()
        self.assertEqual(self.project.official_name, "Renamed coastal rebuild")

    def test_non_owner_cannot_edit_project(self):
        other = make_company(username="other", email="other@corp.com")
        self.client.force_login(other)
        response = self.client.post(
            reverse("projects:edit", args=[self.project.pk]), dict(PROJECT_DATA)
        )
        self.assertEqual(response.status_code, 403)

    def test_draft_project_can_be_deleted_by_owner(self):
        self.client.force_login(self.company)
        response = self.client.post(reverse("projects:delete", args=[self.project.pk]))
        self.assertRedirects(response, reverse("accounts:dashboard"))
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())

    def test_published_project_cannot_be_deleted(self):
        self.project.status = ProjectStatus.PUBLISHED
        self.project.save()
        self.client.force_login(self.company)
        response = self.client.post(reverse("projects:delete", args=[self.project.pk]))
        self.assertRedirects(response, reverse("projects:manage", args=[self.project.pk]))
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
