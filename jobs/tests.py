"""Job board tests: publish, apply, accept/reject, reminders, permissions."""

from datetime import timedelta

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User

from .models import ApplicationStatus, Job, JobApplication, JobStatus
from .services import (
    JobsError,
    apply_to_job,
    decide_application,
    send_deadline_reminders,
)


def make_company(username="corp", email="corp@example.com"):
    return User.objects.create_user(
        username=username,
        email=email,
        password="S3cret!pass",
        role=Role.COMPANY,
        organisation_name="Corp & Fils",
        first_name="Fatou",
        last_name="Ndiaye",
    )


def make_expert(username="awa", email="awa@example.com"):
    return User.objects.create_user(
        username=username,
        email=email,
        password="S3cret!pass",
        role=Role.EXPERT,
        first_name="Awa",
        last_name="Diallo",
    )


def make_job(company, **kwargs):
    defaults = {
        "title": "Senior urban planner",
        "published_by": company,
        "city": "Dakar",
        "country": "Senegal",
        "description": "Lead the urban renewal programme.",
    }
    defaults.update(kwargs)
    return Job.objects.create(**defaults)


class JobModelTests(TestCase):
    def test_is_open_respects_status_and_deadline(self):
        company = make_company()
        open_job = make_job(company)
        self.assertTrue(open_job.is_open)

        closed = make_job(company, status=JobStatus.CLOSED)
        self.assertFalse(closed.is_open)

        past = make_job(company, deadline=timezone.localdate() - timedelta(days=1))
        self.assertFalse(past.is_open)


class ApplyFlowTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.expert = make_expert()
        self.job = make_job(self.company)
        mail.outbox = []

    def test_apply_notifies_both_parties_and_blocks_duplicates(self):
        application = apply_to_job(self.job, self.expert, "I fit this mission.")
        self.assertEqual(application.status, ApplicationStatus.PENDING)
        self.assertEqual(len(mail.outbox), 2)  # expert confirmation + company alert

        with self.assertRaises(JobsError):
            apply_to_job(self.job, self.expert, "again")

    def test_cannot_apply_when_closed_or_own_offer(self):
        closed = make_job(self.company, status=JobStatus.CLOSED)
        with self.assertRaises(JobsError):
            apply_to_job(closed, self.expert, "hello")
        with self.assertRaises(JobsError):
            apply_to_job(self.job, self.company, "self apply")

    def test_accept_then_double_decision_rejected(self):
        application = apply_to_job(self.job, self.expert, "cover letter")
        decide_application(application, self.company, accept=True)
        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.ACCEPTED)
        decision_emails = len(mail.outbox)
        self.assertGreaterEqual(decision_emails, 3)
        with self.assertRaises(JobsError):
            decide_application(application, self.company, accept=False)


class DeadlineReminderTests(TestCase):
    def test_reminders_fire_inside_horizon_only(self):
        from datetime import date

        company = make_company()
        expert = make_expert()
        closing_soon = make_job(
            company, deadline=date.today() + timedelta(days=2)
        )
        far_future = make_job(company, deadline=date.today() + timedelta(days=30))
        apply_to_job(closing_soon, expert, "one")
        apply_to_job(far_future, expert, "two")
        mail.outbox = []

        stats = send_deadline_reminders(days_ahead=3)
        self.assertEqual(stats["experts_reminded"], 1)
        self.assertEqual(stats["companies_reminded"], 1)
        subjects = " ".join(m.subject for m in mail.outbox)
        self.assertIn("closes soon", subjects)


class JobViewTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.expert = make_expert()
        self.job = make_job(self.company)
        self.client = self.client_class()

    def test_public_list_and_detail(self):
        response = self.client.get(reverse("jobs:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.job.title)
        detail = self.client.get(reverse("jobs:detail", args=[self.job.pk]))
        self.assertContains(detail, "Log in to apply")

    def test_create_requires_company_role(self):
        self.client.force_login(self.expert)
        response = self.client.get(reverse("jobs:create"))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.company)
        form_data = {
            "title": "GIS analyst",
            "city": "Thiès",
            "country": "Senegal",
            "contract_type": "consulting",
            "description": "Analyse spatial data.",
            "requirements": "",
            "compensation": "",
            "deadline": "",
        }
        response = self.client.post(reverse("jobs:create"), form_data)
        self.assertEqual(Job.objects.filter(title="GIS analyst").count(), 1)

    def test_apply_through_view_and_review_by_owner_only(self):
        self.client.force_login(self.expert)
        response = self.client.post(
            reverse("jobs:apply", args=[self.job.pk]),
            {"cover_letter": "Ready to start."},
        )
        self.assertRedirects(response, reverse("jobs:my_applications"))
        self.assertEqual(JobApplication.objects.count(), 1)

        stranger = make_expert(username="str", email="str@example.com")
        self.client.force_login(stranger)
        response = self.client.get(reverse("jobs:manage", args=[self.job.pk]))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.company)
        response = self.client.get(reverse("jobs:manage", args=[self.job.pk]))
        self.assertContains(response, "Ready to start.")
        application = JobApplication.objects.get()
        response = self.client.post(
            reverse("jobs:manage", args=[self.job.pk]),
            {"action": "accept", "application_pk": application.pk},
        )
        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.ACCEPTED)

    def test_close_job_stops_applications(self):
        self.client.force_login(self.company)
        self.client.post(
            reverse("jobs:manage", args=[self.job.pk]), {"action": "close"}
        )
        self.job.refresh_from_db()
        self.assertFalse(self.job.is_open)
