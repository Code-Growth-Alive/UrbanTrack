"""Custom User model for Urban Track.

Every account - individual expert, company or donor agency - receives a free,
permanent, unique professional ID (format ``OX-XXXXXX``, spec 02-stack.md).
The ID is immutable once assigned: it anchors cross-confirmed contributions
and public expert profiles, so it must never change nor be recycled.
"""

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as BaseAuthManager
from django.db import models
from django.utils.translation import gettext_lazy as _

from .utils import MAX_ID_GENERATION_ATTEMPTS, generate_professional_id


class Role(models.TextChoices):
    """The three Urban Track account types."""

    EXPERT = "expert", _("Individual expert")
    COMPANY = "company", _("Company / consulting firm")
    DONOR = "donor", _("Donor agency")


class UserManager(BaseAuthManager):
    """Standard auth manager (``create_user``/``create_superuser``) on the custom model."""

    use_in_migrations = True


class User(AbstractUser):
    """
    Urban Track user.

    Roles map directly onto the business model (spec section 1):
      * ``expert``  - free users who confirm contributions and own a public profile;
      * ``company`` - paying clients who publish projects and declare contributors;
      * ``donor``   - strategic partners providing project data (World Bank, AFD...).

    ``professional_id`` is generated at first save and is permanent.
    """

    email = models.EmailField(_("email address"), unique=True)
    role = models.CharField(
        _("role"),
        max_length=20,
        choices=Role.choices,
        default=Role.EXPERT,
        db_index=True,
    )
    organisation_name = models.CharField(
        _("organisation name"),
        max_length=255,
        blank=True,
        help_text=_("Required for company and donor agency accounts."),
    )
    professional_id = models.CharField(
        _("professional ID"),
        max_length=16,
        unique=True,
        editable=False,
        blank=True,
        help_text=_(
            "Permanent, free, unique professional ID (OX-XXXXXX). "
            "Assigned at creation, never modified."
        ),
    )

    REQUIRED_FIELDS = ["email"]

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.professional_id})"

    def save(self, *args, **kwargs):
        """Normalise the email domain part and assign the professional ID.

        The ID candidate is checked against existing rows before saving; the
        database unique constraint remains the concurrency backstop. Any other
        ``IntegrityError`` (e.g. duplicate email/username) propagates untouched.
        """
        self.email = User.objects.normalize_email(self.email)
        if not self.professional_id:
            for _attempt in range(MAX_ID_GENERATION_ATTEMPTS):
                candidate = generate_professional_id()
                if not User.objects.filter(professional_id=candidate).exists():
                    self.professional_id = candidate
                    break
            else:
                raise RuntimeError(
                    "Could not allocate a unique professional ID after "
                    f"{MAX_ID_GENERATION_ATTEMPTS} attempts."
                )
        return super().save(*args, **kwargs)

    @property
    def is_expert(self):
        return self.role == Role.EXPERT

    @property
    def is_company(self):
        return self.role == Role.COMPANY

    @property
    def is_donor(self):
        return self.role == Role.DONOR

    @property
    def initials(self):
        """Avatar initials from the name, falling back to the username."""
        parts = f"{self.first_name} {self.last_name}".split()
        if parts:
            return "".join(part[0] for part in parts[:2]).upper()
        cleaned = self.username.replace("@", " ").strip()
        return (cleaned[:2].upper() or "?")


class CvTemplate(models.TextChoices):
    """Pluggable CV skins consumed by the cv_generator app (Epic 7)."""

    ACADEMIC_HARVARD_MIT = "academic_harvard_mit", _("Academic (Harvard/MIT)")
    AFD = "afd", _("AFD")
    WORLD_BANK = "world_bank", _("World Bank")


class Skill(models.Model):
    """A professional skill tag attachable to expert portfolios."""

    name = models.CharField(_("name"), max_length=120, unique=True)

    class Meta:
        verbose_name = _("skill")
        verbose_name_plural = _("skills")
        ordering = ["name"]

    def __str__(self):
        return self.name


class ExpertProfile(models.Model):
    """
    Public portfolio of an individual expert (ResearchGate-style profile).

    Fed exclusively by cross-confirmed data: ``confirmed`` contributions
    surface on the public profile; self-declared content lives here only as
    context (headline, bio, skills, trainings) and never counts toward the
    certification badge.

    ``cv_template`` is reserved now for the multi-template CV generator
    (Epic 7): it records which skin the expert prefers.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="expert_profile",
        verbose_name=_("user"),
    )
    headline = models.CharField(_("headline"), max_length=255, blank=True)
    bio = models.TextField(_("bio"), blank=True)
    city = models.CharField(_("city"), max_length=120, blank=True)
    country = models.CharField(
        _("country"), max_length=120, blank=True,
        help_text=_("ISO country name; supports pan-African then international scaling."),
    )
    skills = models.ManyToManyField(
        Skill, blank=True, related_name="experts", verbose_name=_("skills")
    )
    cv_template = models.CharField(
        _("CV template"),
        max_length=40,
        choices=CvTemplate.choices,
        default=CvTemplate.ACADEMIC_HARVARD_MIT,
        help_text=_("Reserved for the CV generator (Epic 7)."),
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("expert profile")
        verbose_name_plural = _("expert profiles")

    def __str__(self):
        return f"Profile of {self.user} ({self.user.professional_id})"

    def get_absolute_url(self):
        """Public URL anchored to the permanent OX-ID (traceability)."""
        from django.urls import reverse

        return reverse("accounts:public_profile", args=[self.user.professional_id])

    def confirmed_contributions(self):
        """Certified experiences only: the public-profile contract."""
        from certification.models import ContributionStatus

        return self.user.contributions.filter(
            status=ContributionStatus.CONFIRMED
        ).select_related("project", "expert").order_by("-project__duration_start")

    def trust_score(self):
        """
        RG-Score equivalent: certified contributions weighted by role.

        Director 4 / Manager 3 / Specialist 2 / Assistant 1. Defined here in
        Epic 1 so Epic 4's UI and Epic 10's matchmaking share one definition.
        """
        weights = {
            "director": 4,
            "manager": 3,
            "specialist": 2,
            "assistant": 1,
        }
        score = 0
        for contribution in self.confirmed_contributions():
            score += weights.get(contribution.role_type, 1)
        return score


class Training(models.Model):
    """A training entry of an expert portfolio (contextual, non-certifying)."""

    profile = models.ForeignKey(
        ExpertProfile,
        on_delete=models.CASCADE,
        related_name="trainings",
        verbose_name=_("profile"),
    )
    title = models.CharField(_("title"), max_length=255)
    institution = models.CharField(_("institution"), max_length=255)
    year = models.PositiveIntegerField(_("year"), null=True, blank=True)

    class Meta:
        verbose_name = _("training")
        verbose_name_plural = _("trainings")
        ordering = ["-year", "title"]

    def __str__(self):
        return f"{self.title} ({self.institution})"
