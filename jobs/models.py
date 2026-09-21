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
    OPEN = "open", _("Ouverte")
    CLOSED = "closed", _("Clôturée")


class ContractType(models.TextChoices):
    FULL_TIME = "full_time", _("Temps plein")
    PART_TIME = "part_time", _("Temps partiel")
    CONSULTING = "consulting", _("Consultance")
    MISSION = "mission", _("Mission courte")


class Job(models.Model):
    """A job offer published by any user."""

    title = models.CharField(_("titre"), max_length=200)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="published_jobs",
        verbose_name=_("publiée par"),
    )
    city = models.CharField(_("ville"), max_length=120)
    country = models.CharField(_("pays"), max_length=120)
    contract_type = models.CharField(
        _("type de contrat"),
        max_length=20,
        choices=ContractType.choices,
        default=ContractType.FULL_TIME,
    )
    description = models.TextField(
        _("description"), help_text=_("Mission, responsabilités, contexte de l'équipe.")
    )
    requirements = models.TextField(_("prérequis"), blank=True)
    compensation = models.CharField(
        _("rémunération"),
        max_length=200,
        blank=True,
        help_text=_("ex. « Compétitive », une fourchette, ou laissez vide."),
    )
    deadline = models.DateField(
        _("date limite de candidature"),
        null=True,
        blank=True,
        help_text=_("Facultatif : les candidatures restent ouvertes si vide."),
    )
    status = models.CharField(
        _("statut"),
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.OPEN,
        db_index=True,
    )
    created_at = models.DateTimeField(_("créée le"), auto_now_add=True)
    updated_at = models.DateTimeField(_("mise à jour le"), auto_now=True)

    class Meta:
        verbose_name = _("mission")
        verbose_name_plural = _("missions")
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
    PENDING = "pending", _("En cours d'examen")
    ACCEPTED = "accepted", _("Acceptée")
    REJECTED = "rejected", _("Non retenue")


class JobApplication(models.Model):
    """One expert's application to a job."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="applications")
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="job_applications",
        limit_choices_to={"role": "user"},
        verbose_name=_("candidat"),
    )
    cover_letter = models.TextField(
        _("lettre de motivation"),
        help_text=_(
            "En quoi vous correspondez à cette mission : l'expérience certifiée parle en premier."
        ),
    )
    status = models.CharField(
        _("statut"),
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.PENDING,
    )
    applied_at = models.DateTimeField(_("candidature déposée le"), auto_now_add=True)
    decided_at = models.DateTimeField(_("décidée le"), null=True, blank=True)

    class Meta:
        verbose_name = _("candidature")
        verbose_name_plural = _("candidatures")
        ordering = ["-applied_at"]
        constraints = [
            models.UniqueConstraint(fields=["job", "applicant"], name="unique_application_per_job"),
        ]

    def __str__(self):
        return f"{self.applicant} → {self.job}"
