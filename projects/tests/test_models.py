"""Tests for the Project model and the publishing flow."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase

from ..models import Project, ProjectStatus, ProjectVisibility
from ..services import PublishingError, archive_project, publish_project

User = get_user_model()


def make_company(username="btp", email=None):
    return User.objects.create_user(
        username=username,
        email=email or f"{username}@example.com",
        role="company",
        organisation_name="BTP & Urbanisme SARL",
        password="S3cret!pass",
    )


def make_project(company, **overrides):
    defaults = dict(
        official_name="Rehabilitation of the Grand Marche district",
        description="Urban renewal of a central market district.",
        deliverables="Master plan\nDetailed engineering designs\nWorks supervision",
        duration_start=date(2024, 1, 15),
        duration_end=date(2025, 6, 30),
        budget=2500000.00,
        client_name="Municipality of Cotonou",
        published_by=company,
    )
    defaults.update(overrides)
    return Project.objects.create(**defaults)


class ProjectModelTests(TestCase):
    def setUp(self):
        self.company = make_company()

    def test_defaults_are_draft_and_private(self):
        project = make_project(self.company)
        self.assertEqual(project.status, ProjectStatus.DRAFT)
        self.assertEqual(project.visibility, ProjectVisibility.PRIVATE)

    def test_duration_check_constraint(self):
        with self.assertRaises(IntegrityError):
            make_project(
                self.company,
                duration_start=date(2025, 1, 1),
                duration_end=date(2024, 1, 1),
            )

    def test_clean_rejects_inverted_dates_before_save(self):
        project = Project(
            official_name="X",
            description="x",
            deliverables="x",
            duration_start=date(2025, 1, 1),
            duration_end=date(2024, 1, 1),
            client_name="Client",
            published_by=self.company,
        )
        with self.assertRaises(ValidationError) as ctx:
            project.clean()
        self.assertIn("duration_end", ctx.exception.message_dict)

    def test_ongoing_project_allows_null_end(self):
        project = make_project(self.company, duration_end=None)
        project.full_clean()
        self.assertIsNone(project.duration_end)

    def test_public_visibility_gate(self):
        project = make_project(self.company)
        self.assertFalse(project.is_publicly_visible)
        project.status = ProjectStatus.PUBLISHED
        self.assertFalse(project.is_publicly_visible)
        project.visibility = ProjectVisibility.PUBLIC
        self.assertTrue(project.is_publicly_visible)

    def test_deliverables_lines_helper(self):
        project = make_project(self.company, deliverables="A\n B \n\nC")
        self.assertEqual(project.deliverables_lines, ["A", "B", "C"])

    def test_str_is_official_name(self):
        project = make_project(self.company)
        self.assertEqual(str(project), project.official_name)


class PublishingFlowTests(TestCase):
    def setUp(self):
        self.company = make_company()

    def test_publish_flips_status(self):
        project = make_project(self.company)
        publish_project(project)
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.PUBLISHED)

    def test_only_draft_can_be_published(self):
        project = make_project(self.company, status=ProjectStatus.ARCHIVED)
        with self.assertRaises(PublishingError):
            publish_project(project)

    def test_invalid_project_cannot_be_published(self):
        project = make_project(self.company)
        project.duration_start = date(2025, 1, 1)
        project.duration_end = date(2024, 1, 1)
        with self.assertRaises(ValidationError):
            publish_project(project)
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.DRAFT)

    def test_archive_requires_published(self):
        project = make_project(self.company)
        with self.assertRaises(PublishingError):
            archive_project(project)
        publish_project(project)
        archive_project(project)
        self.assertEqual(project.status, ProjectStatus.ARCHIVED)

    def test_publish_dispatches_invitations_to_unknown_experts(self):
        from certification.models import ExpertInvitation

        project = make_project(self.company)
        from certification.models import RoleType
        from certification.services import declare_contributor

        declare_contributor(
            project,
            email="unknown.expert@example.com",
            role_type=RoleType.MANAGER,
            contribution_bullets="Led the works supervision team.",
            added_by=self.company,
        )
        publish_project(project)
        invitation = ExpertInvitation.objects.get()
        self.assertEqual(invitation.email, "unknown.expert@example.com")
        self.assertTrue(invitation.is_active)
        expected_expiry = invitation.sent_at + timedelta(days=14)
        self.assertAlmostEqual(
            invitation.expires_at.timestamp(),
            expected_expiry.timestamp(),
            delta=5,
        )
