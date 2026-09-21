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
    """Real role on a project (T6): wider and extensible than the original 4.

    Mirrors the ROLE_LABELS used by the CV engine so every role renders in
    FR/EN exports. Trust-score weights live in ``ExpertProfile.trust_score``.
    """

    DIRECTOR = "director", _("Directeur")
    MANAGER = "manager", _("Responsable")
    ASSISTANT = "assistant", _("Assistant")
    SPECIALIST = "specialist", _("Spécialiste")
    CONSULTANT = "consultant", _("Consultant")
    ENGINEER = "engineer", _("Ingénieur")
    OTHER = "other", _("Autre")


class ContributionStatus(models.TextChoices):
    """Mandated lifecycle: invited -> pending_confirmation -> confirmed/rejected/disputed."""

    INVITED = "invited", _("Invité")
    PENDING_CONFIRMATION = "pending_confirmation", _("En attente de confirmation")
    CONFIRMED = "confirmed", _("Confirmé")
    REJECTED = "rejected", _("Refusé")
    DISPUTED = "disputed", _("Contesté")

    @classmethod
    def actionable(cls):
        """States from which the expert can still act."""
        return {cls.INVITED, cls.PENDING_CONFIRMATION}

    @classmethod
    def terminal(cls):
        return {cls.REJECTED}


class ConfirmationSource(models.TextChoices):
    """
    Who is expected to provide the counter-signature on a contribution (T1).

    * ``expert``      — the named expert personally confirms (default path);
    * ``client``      — the client / maître d'ouvrage confirms a sole-trader
      or small consultancy lead (consultant individuel);
    * ``lead_firm``   — the leader of a groupement confirms a sub-contracted
      member (declaration by the chef de file).
    """

    EXPERT = "expert", _("Expert nommé")
    CLIENT = "client", _("Client / maître d'ouvrage")
    LEAD_FIRM = "lead_firm", _("Groupement / entreprise mandataire")


class InvitationStatus(models.TextChoices):
    SENT = "sent", _("Envoyée")
    OPENED = "opened", _("Ouverte")
    CONVERTED = "converted", _("Convertie")
    EXPIRED = "expired", _("Expirée")


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
      * ``pending_company_validation``: distinguishes "awaiting the expert's
        first answer" from "the company must re-validate an adjusted wording",
        which share the same status value;
      * ``dispute_reason`` / ``rejection_reason``: audit trail for admin
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
        verbose_name=_("projet"),
    )
    expert = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contributions",
        limit_choices_to=models.Q(email_confirmed=True),
        verbose_name=_("expert"),
    )
    invited_email = models.EmailField(
        _("Email de l'invité"),
        help_text=_(
            "Email utilisé pour joindre l'expert ; reflète l'email du compte lié "
            "lorsque l'expert existe déjà (règle de déduplication 5)."
        ),
    )
    role_type = models.CharField(_("type de rôle"), max_length=20, choices=RoleType.choices)
    contribution_bullets = models.TextField(
        _("Réalisations"),
        help_text=_("Une réalisation par ligne décrivant ce que l'expert a réellement livré."),
    )
    status = models.CharField(
        _("statut"),
        max_length=30,
        choices=ContributionStatus.choices,
        default=ContributionStatus.INVITED,
        db_index=True,
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="declared_contributions",
        limit_choices_to=models.Q(email_confirmed=True),
        verbose_name=_("ajouté par"),
    )
    confirmed_at = models.DateTimeField(_("confirmé le"), null=True, blank=True)

    pending_company_validation = models.BooleanField(default=False, editable=False)
    rejection_reason = models.TextField(_("motif de refus"), blank=True)
    dispute_reason = models.TextField(_("motif de contestation"), blank=True)

    # T1: which counter-signature is expected, and where the confirmation
    # actually came from. ``confirmation_source`` is declared when the
    # contribution is created; ``confirmed_by`` records the physical actor
    # who validated it ("expert" or "client") once ``status == confirmed``.
    confirmation_source = models.CharField(
        _("source de confirmation"),
        max_length=20,
        choices=ConfirmationSource.choices,
        default=ConfirmationSource.EXPERT,
        help_text=_(
            "Qui doit contre-signer cette contribution : l'expert nommé, le "
            "client / maître d'ouvrage, ou le groupement / entreprise mandataire."
        ),
    )
    confirmed_by = models.CharField(
        _("confirmé par"),
        max_length=20,
        choices=ConfirmationSource.choices,
        blank=True,
        help_text=_("Quel acteur contre-signataire a réellement validé la contribution."),
    )
    # One-time secret token for the unauthenticated client-confirmation path.
    client_confirm_token = models.UUIDField(
        _("jeton de confirmation client"),
        unique=True,
        null=True,
        blank=True,
        editable=False,
        help_text=_(
            "Jeton secret à usage unique envoyé par email au client / maître d'ouvrage "
            "pour confirmer une contribution sans nécessiter de compte (T1)."
        ),
    )

    created_at = models.DateTimeField(_("créé le"), auto_now_add=True)
    updated_at = models.DateTimeField(_("mis à jour le"), auto_now=True)

    class Meta:
        verbose_name = _("contribution de projet")
        verbose_name_plural = _("contributions de projet")
        ordering = ["project_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=("project", "invited_email", "role_type"),
                name="uniq_contribution_project_email_role",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="confirmed") | models.Q(confirmed_at__isnull=False),
                name="confirmed_contribution_has_confirmed_at",
            ),
        ]

    def __str__(self):
        target = self.expert or self.invited_email
        return f"{target}: {self.get_role_type_display()} on {self.project}"

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
            old = (
                ProjectContribution.objects.filter(pk=self.pk)
                .values(*self.PROTECTED_FIELDS, "status")
                .first()
            )
            tampered = [
                field for field in self.PROTECTED_FIELDS if old[field] != getattr(self, field)
            ]
            if (
                old["status"] == ContributionStatus.CONFIRMED
                and self.status == ContributionStatus.CONFIRMED
                and tampered
            ):
                raise ValidationError(
                    {
                        field: _(
                            "Cette contribution est certifiée ; toute modification "
                            "nécessite de démarrer un nouveau cycle de validation."
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
        """Bullets as a list: one per line in the stored text."""
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
    token = models.UUIDField(_("jeton"), unique=True, editable=False, default=uuid.uuid4)
    sent_at = models.DateTimeField(_("envoyé le"), auto_now_add=True)
    expires_at = models.DateTimeField(_("expire le"))
    status = models.CharField(
        _("statut"),
        max_length=20,
        choices=InvitationStatus.choices,
        default=InvitationStatus.SENT,
        db_index=True,
    )
    reminder_count = models.PositiveSmallIntegerField(_("nombre de relances"), default=0)

    class Meta:
        verbose_name = _("invitation d'expert")
        verbose_name_plural = _("invitations d'expert")
        ordering = ["-sent_at"]

    def __str__(self):
        return f"Invite for {self.email} ({self.status})"

    @property
    def is_active(self):
        from django.utils import timezone

        return self.status != InvitationStatus.EXPIRED and self.expires_at > timezone.now()

    @property
    def magic_link_path(self):
        """Relative URL of the pre-filled landing page (Epic 3 route)."""
        return f"/certification/invitations/{self.token}/"

    def save(self, *args, **kwargs):
        from datetime import timedelta

        from django.utils import timezone

        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=settings.INVITATION_EXPIRY_DAYS)
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)
