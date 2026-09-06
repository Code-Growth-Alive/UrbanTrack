"""
Job board models (Epic 8): companies publish job offers; experts apply;
the company accepts or declines; reminders nudge before deadlines.
"""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class JobStatus(models.TextChoices):
    OPEN = "open", _("Open")
    CLOSED = "closed", _("Closed")


class ContractType(models.TextChoices):
    FULL_TIME = "full_time", _("Full-time")
    PART_TIME = "part_time", _("Part-time")
    CONSULTING = "consulting", _("Consulting")
    MISSION = "mission", _("Short mission")


class Job(models.Model):
    """A job offer published by any user."""

    title = models.CharField(_("title"), max_length=200)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="published_jobs",
        verbose_name=_("published by"),
    )
    city = models.CharField(_("city"), max_length=120)
    country = models.CharField(_("country"), max_length=120)
    contract_type = models.CharField(
        _("contract type"),
        max_length=20,
        choices=ContractType.choices,
        default=ContractType.FULL_TIME,
    )
    description = models.TextField(
        _("description"), help_text=_("Mission, responsibilities, team context.")
    )
    requirements = models.TextField(_("requirements"), blank=True)
    compensation = models.CharField(
        _("compensation"),
        max_length=200,
        blank=True,
        help_text=_("e.g. “Competitive”, a range, or leave empty."),
    )
    deadline = models.DateField(
        _("application deadline"),
        null=True,
        blank=True,
        help_text=_("Optional: applications stay open when empty."),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.OPEN,
        db_index=True,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("job")
        verbose_name_plural = _("jobs")
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("jobs:detail", args=[self.pk])

    @property
    def is_open(self):
        """Open for applications: not closed and past no deadline."""
        if self.status != JobStatus.OPEN:
            return False
        return not (self.deadline and timezone.localdate() > self.deadline)

    @property
    def days_until_deadline(self):
        if not self.deadline:
            return None
        return (self.deadline - timezone.localdate()).days

    @property
    def requirements_lines(self):
        return [line.strip() for line in self.requirements.splitlines() if line.strip()]

    def application_for(self, user):
        """The requesting expert's existing application, or None."""
        if not user.is_authenticated:
            return None
        return self.applications.filter(applicant=user).first()


class ApplicationStatus(models.TextChoices):
    PENDING = "pending", _("Pending review")
    ACCEPTED = "accepted", _("Accepted")
    REJECTED = "rejected", _("Not retained")


class JobApplication(models.Model):
    """One expert's application to a job."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="applications")
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="job_applications",
        limit_choices_to={"role": "user"},
        verbose_name=_("applicant"),
    )
    cover_letter = models.TextField(
        _("cover letter"),
        help_text=_("Why you fit this mission: certified experience speaks first."),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.PENDING,
    )
    applied_at = models.DateTimeField(_("applied at"), auto_now_add=True)
    decided_at = models.DateTimeField(_("decided at"), null=True, blank=True)

    class Meta:
        verbose_name = _("job application")
        verbose_name_plural = _("job applications")
        ordering = ["-applied_at"]
        constraints = [
            models.UniqueConstraint(fields=["job", "applicant"], name="unique_application_per_job"),
        ]

    def __str__(self):
        return f"{self.applicant} → {self.job}"
