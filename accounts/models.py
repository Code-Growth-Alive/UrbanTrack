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
