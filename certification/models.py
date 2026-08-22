"""
The heart of Urban Track: cross-confirmed contributions and expert invitations.

ResearchGate mapping (spec section 1):
  * ``ProjectContribution`` is the "co-authorship claim" made by a company;
    it only becomes credible once the named expert personally confirms it.
  * ``ExpertInvitation`` is the "is this you?" email invite for experts who
    do not have an account yet, carrying a magic-link token.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class RoleType(models.TextChoices):
    DIRECTOR = "director", _("Director")
    MANAGER = "manager", _("Manager")
    ASSISTANT = "assistant", _("Assistant")
    SPECIALIST = "specialist", _("Specialist")


class ContributionStatus(models.TextChoices):
    """Mandated lifecycle: invited -> pending_confirmation -> confirmed/rejected/disputed."""

    INVITED = "invited", _("Invited")
    PENDING_CONFIRMATION = "pending_confirmation", _("Pending confirmation")
    CONFIRMED = "confirmed", _("Confirmed")
    REJECTED = "rejected", _("Rejected")
    DISPUTED = "disputed", _("Disputed")

    @classmethod
    def actionable(cls):
        """States from which the expert can still act."""
        return {cls.INVITED, cls.PENDING_CONFIRMATION}

    @classmethod
    def terminal(cls):
        return {cls.REJECTED}


class InvitationStatus(models.TextChoices):
    SENT = "sent", _("Sent")
    OPENED = "opened", _("Opened")
    CONVERTED = "converted", _("Converted")
    EXPIRED = "expired", _("Expired")


class ProjectContribution(models.Model):
    """
    A declared contribution of one expert to one project.

    Certification relies SOLELY on independent double confirmation
    (business rule 3): ``status`` becomes ``confirmed`` only after the
    expert personally validates what the company declared.

    Integrity rule 8: once ``confirmed``, the certified data cannot be
    silently modified. Any change of a protected field must go through a new
    validation cycle (``pending_company_validation=True`` +
    ``status=pending_confirmation``) enforced in :meth:`save` and in
    ``certification.services``.

    Additive fields beyond the mandated list (flagged deviation):
      * ``pending_company_validation`` — distinguishes "awaiting the expert's
        first answer" from "the company must re-validate an adjusted wording",
        which share the same status value;
      * ``dispute_reason`` / ``rejection_reason`` — audit trail for admin
        arbitration (rule 7).
    """

    PROTECTED_FIELDS = (
        "project",
        "expert",
        "role_type",
        "contribution_bullets",
        "invited_email",
    )

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="contributions",
        verbose_name=_("project"),
    )
    expert = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contributions",
        limit_choices_to=models.Q(role="expert") | models.Q(is_superuser=True),
        verbose_name=_("expert"),
    )
    invited_email = models.EmailField(
        _("invited email"),
        help_text=_(
            "Email used to reach the expert; mirrors the linked account email "
            "when the expert already exists (deduplication rule 5)."
        ),
    )
    role_type = models.CharField(_("role type"), max_length=20, choices=RoleType.choices)
    contribution_bullets = models.TextField(
        _("contribution bullets"),
        help_text=_("One bullet per line describing what the expert actually delivered."),
    )
    status = models.CharField(
        _("status"),
        max_length=30,
        choices=ContributionStatus.choices,
        default=ContributionStatus.INVITED,
        db_index=True,
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="declared_contributions",
        limit_choices_to=models.Q(role="company") | models.Q(is_superuser=True),
        verbose_name=_("added by"),
    )
    confirmed_at = models.DateTimeField(_("confirmed at"), null=True, blank=True)

    pending_company_validation = models.BooleanField(default=False, editable=False)
    rejection_reason = models.TextField(_("rejection reason"), blank=True)
    dispute_reason = models.TextField(_("dispute reason"), blank=True)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("project contribution")
        verbose_name_plural = _("project contributions")
        ordering = ["project_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=("project", "invited_email", "role_type"),
                name="uniq_contribution_project_email_role",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="confirmed")
                | models.Q(confirmed_at__isnull=False),
                name="confirmed_contribution_has_confirmed_at",
            ),
        ]

    def __str__(self):
        target = self.expert or self.invited_email
        return f"{target} — {self.get_role_type_display()} on {self.project}"

    def clean(self):
        if self.added_by_id and self.added_by_id == self.expert_id and self.expert_id:
            raise ValidationError(_("The declaring company and the expert must differ."))

    def save(self, *args, **kwargs):
        """Normalise the invitation email and enforce certification integrity.

        Rule 5 (auto-link): when the invited email matches an existing expert
        account, the contribution links to it instead of creating a duplicate.
        Rule 8 (immutability): a modification of a protected field on a
        ``confirmed`` contribution is refused unless the same save also leaves
        the ``confirmed`` state (i.e. starts a new validation cycle).
        """
        self.invited_email = self.invited_email.strip().lower()
        if self.expert_id and not self.pk:
            # Auto-link on creation: mirror the account email exactly.
            self.invited_email = self.expert.email

        if self.pk:
            old = ProjectContribution.objects.filter(pk=self.pk).values(
                *self.PROTECTED_FIELDS, "status"
            ).first()
            tampered = [
                field
                for field in self.PROTECTED_FIELDS
                if old[field] != getattr(self, field)
            ]
            if (
                old["status"] == ContributionStatus.CONFIRMED
                and self.status == ContributionStatus.CONFIRMED
                and tampered
            ):
                raise ValidationError(
                    {
                        field: _(
                            "This contribution is certified; modifying it requires "
                            "starting a new validation cycle."
                        )
                        for field in tampered
                    }
                )
        super().save(*args, **kwargs)

    @property
    def is_certified(self):
        return self.status == ContributionStatus.CONFIRMED

    @property
    def contribution_bullets_lines(self):
        """Bullets as a list — one per line in the stored text."""
        return [line.strip() for line in self.contribution_bullets.splitlines() if line.strip()]


class ExpertInvitation(models.Model):
    """
    Magic-link invitation addressed to an unregistered expert (rule 2).

    The token is a UUID4 kept secret until expiry (~14 days, business rule 6);
    reminders are tracked so the scheduled task never exceeds two.
    """

    contribution = models.ForeignKey(
        ProjectContribution,
        on_delete=models.CASCADE,
        related_name="invitations",
        verbose_name=_("contribution"),
    )
    email = models.EmailField(_("email"))
    token = models.UUIDField(
        _("token"), unique=True, editable=False, default=uuid.uuid4
    )
    sent_at = models.DateTimeField(_("sent at"), auto_now_add=True)
    expires_at = models.DateTimeField(_("expires at"))
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=InvitationStatus.choices,
        default=InvitationStatus.SENT,
        db_index=True,
    )
    reminder_count = models.PositiveSmallIntegerField(_("reminder count"), default=0)

    class Meta:
        verbose_name = _("expert invitation")
        verbose_name_plural = _("expert invitations")
        ordering = ["-sent_at"]

    def __str__(self):
        return f"Invite for {self.email} ({self.status})"

    @property
    def is_active(self):
        from django.utils import timezone

        return (
            self.status != InvitationStatus.EXPIRED
            and self.expires_at > timezone.now()
        )

    @property
    def magic_link_path(self):
        """Relative URL of the pre-filled landing page (Epic 3 route)."""
        return f"/certification/invitations/{self.token}/"

    def save(self, *args, **kwargs):
        from datetime import timedelta

        from django.utils import timezone

        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(
                days=settings.INVITATION_EXPIRY_DAYS
            )
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)
