"""Tests for the system admin dashboard and cross-app management views."""

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from jobs.models import ApplicationStatus, JobApplication
from jobs.tests import make_company, make_expert, make_job
from projects.tests.test_models import make_project


def make_superuser():
    return User.objects.create_superuser(
        username="root",
        email="root@example.com",
        password="S3cret!pass",
        role=Role.ADMIN,
    )


class AdminAccessTests(TestCase):
    def setUp(self):
        self.admin = make_superuser()

    def _get(self, name, **kwargs):
        return self.client.get(reverse(name, **kwargs))

    def test_anonymous_redirected_to_login(self):
        response = self._get("adminpanel:dashboard")
        self.assertEqual(response.status_code, 302)

    def test_non_staff_denied(self):
        expert = make_expert()
        self.client.force_login(expert)
        self.assertEqual(self._get("adminpanel:dashboard").status_code, 403)

    def test_admin_role_can_access_dashboard(self):
        staff = make_expert()
        staff.role = Role.ADMIN
        staff.save(update_fields=["role"])
        self.client.force_login(staff)
        self.assertEqual(self._get("adminpanel:dashboard").status_code, 200)


class AdminDashboardTests(TestCase):
    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)
        self.company = make_company()
        self.expert = make_expert()
        self.project = make_project(self.company)
        job = make_job(self.company)
        JobApplication.objects.create(job=job, applicant=self.expert, cover_letter="Ready.")

    def test_dashboard_shows_counts(self):
        response = self.client.get(reverse("adminpanel:dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        for label in ("Total des comptes", "Projets publiés", "Emplois ouverts", "Candidatures"):
            self.assertIn(label, content)

    def test_dashboard_breaks_down_roles(self):
        response = self.client.get(reverse("adminpanel:dashboard"))
        content = response.content.decode()
        self.assertIn("Utilisateurs", content)
        self.assertIn("Administrateurs", content)
        self.assertIn("Emails confirmés", content)


class AdminUserManagementTests(TestCase):
    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)
        self.expert = make_expert()
        self.company = make_company()

    def test_user_list_shows_all_accounts_and_filters(self):
        response = self.client.get(reverse("adminpanel:user_list"))
        self.assertContains(response, self.expert.professional_id)
        self.assertContains(response, self.company.professional_id)

        self.expert.role = Role.ADMIN
        self.expert.save(update_fields=["role"])
        response = self.client.get(reverse("adminpanel:user_list"), {"role": "admin"})
        self.assertContains(response, self.expert.professional_id)
        self.assertNotContains(response, self.company.professional_id)

    def test_admin_can_edit_user_role(self):
        response = self.client.post(
            reverse("adminpanel:user_edit", args=[self.expert.pk]),
            {
                "first_name": self.expert.first_name,
                "last_name": self.expert.last_name,
                "role": "user",
                "is_active": "on",
                "is_staff": "",
                "is_superuser": "",
                "password": "",
            },
        )
        self.assertRedirects(response, reverse("adminpanel:user_list"))
        self.expert.refresh_from_db()
        self.assertEqual(self.expert.role, Role.USER)

    def test_creating_expert_profile_via_admin_edit(self):
        profile_gone = make_expert(username="noprofile", email="noprofile@example.com")
        profile_gone.expert_profile.delete()
        self.client.post(
            reverse("adminpanel:user_edit", args=[profile_gone.pk]),
            {
                "first_name": profile_gone.first_name,
                "last_name": profile_gone.last_name,
                "role": "user",
                "is_active": "on",
                "is_staff": "",
                "is_superuser": "",
                "password": "",
            },
        )
        profile_gone.refresh_from_db()
        self.assertTrue(hasattr(profile_gone, "expert_profile"))

    def test_admin_can_set_new_password(self):
        response = self.client.post(
            reverse("adminpanel:user_edit", args=[self.expert.pk]),
            {
                "first_name": self.expert.first_name,
                "last_name": self.expert.last_name,
                "role": "user",
                "is_active": "on",
                "is_staff": "",
                "is_superuser": "",
                "password": "N3w.AdminPass!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.expert.refresh_from_db()
        self.assertTrue(self.expert.check_password("N3w.AdminPass!"))

    def test_admin_can_deactivate_reactivate_user(self):
        self.client.post(reverse("adminpanel:user_toggle", args=[self.expert.pk]))
        self.expert.refresh_from_db()
        self.assertFalse(self.expert.is_active)
        self.client.post(reverse("adminpanel:user_toggle", args=[self.expert.pk]))
        self.expert.refresh_from_db()
        self.assertTrue(self.expert.is_active)

    def test_cannot_deactivate_own_account(self):
        response = self.client.post(reverse("adminpanel:user_toggle", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(response.status_code, 302)

    def test_admin_can_delete_user(self):
        response = self.client.post(reverse("adminpanel:user_delete", args=[self.expert.pk]))
        self.assertRedirects(response, reverse("adminpanel:user_list"))
        self.assertFalse(User.objects.filter(pk=self.expert.pk).exists())


class AdminListingsTests(TestCase):
    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)
        self.company = make_company()
        self.expert = make_expert()
        self.project = make_project(self.company)
        self.job = make_job(self.company)
        self.application = JobApplication.objects.create(
            job=self.job, applicant=self.expert, cover_letter="Ready."
        )

    def test_job_list_shows_all_offers(self):
        response = self.client.get(reverse("adminpanel:job_list"))
        self.assertContains(response, self.job.title)

    def test_project_list_shows_all_projects(self):
        response = self.client.get(reverse("adminpanel:project_list"))
        self.assertContains(response, self.project.official_name)

    def test_application_list_shows_and_filters(self):
        response = self.client.get(reverse("adminpanel:application_list"))
        content = response.content.decode()
        self.assertIn(self.expert.get_full_name(), content)

        response = self.client.get(
            reverse("adminpanel:application_list"), {"status": ApplicationStatus.ACCEPTED}
        )
        self.assertNotIn(self.application.applicant.email, response.content.decode())
