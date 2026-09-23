from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as BaseAuthManager
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .utils import MAX_ID_GENERATION_ATTEMPTS, generate_professional_id


class Role(models.TextChoices):
    """The two Urban Track account types."""

    USER = "user", _("Utilisateur")
    ADMIN = "admin", _("Administrateur")


class CompanyRole(models.TextChoices):
    """Role of a user inside a company (T2)."""

    ADMIN = "admin", _("Administrateur")
    MEMBER = "member", _("Membre")


class MembershipStatus(models.TextChoices):
    """Lifecycle of a company affiliation request (T2)."""

    REQUESTED = "requested", _("Demandée")
    INVITED = "invited", _("Invitée")
    APPROVED = "approved", _("Approuvée")
    DECLINED = "declined", _("Refusée")


class Company(models.Model):
    """
    An organisation (company, agency, firm) that a user belongs to.

    Created case-insensitively on the unique ``name`` when a user signs up:
    the founder becomes its first administrator with an approved membership.
    Joining an EXISTING company is never implicit (T2): the candidate gets a
    ``CompanyMembership`` in ``requested`` state and only appears as a member
    once an administrator approves it.

    ``User.company`` is populated only for approved members, so public pages
    (team, project declarations, job publisher name) never leak a
    non-approved affiliation.
    """

    name = models.CharField(_("nom"), max_length=255, unique=True)
    country = models.CharField(_("pays"), max_length=120, blank=True)
    founded_year = models.PositiveIntegerField(_("année de création"), null=True, blank=True)
    size = models.CharField(_("taille"), max_length=120, blank=True)
    domains = models.JSONField(_("domaines"), default=list, blank=True)
    accreditations = models.JSONField(_("accréditations"), default=list, blank=True)
    website = models.URLField(_("site web"), blank=True)
    description = models.TextField(_("description"), blank=True)

    class Meta:
        verbose_name = _("structure")
        verbose_name_plural = _("structures")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("accounts:company_public", args=[self.pk])

    def is_admin(self, user):
        """True when ``user`` holds an approved administrator role here."""
        if not getattr(user, "is_authenticated", False):
            return False
        return CompanyMembership.objects.filter(
            user=user,
            company=self,
            role=CompanyRole.ADMIN,
            status=MembershipStatus.APPROVED,
        ).exists()

    def is_member(self, user):
        """True when ``user`` has an approved membership here."""
        if not getattr(user, "is_authenticated", False):
            return False
        return CompanyMembership.objects.filter(
            user=user, company=self, status=MembershipStatus.APPROVED
        ).exists()

    def admins(self):
        return User.objects.filter(
            company_memberships__company=self,
            company_memberships__role=CompanyRole.ADMIN,
            company_memberships__status=MembershipStatus.APPROVED,
        )

    def approved_members(self):
        return User.objects.filter(
            company_memberships__company=self,
            company_memberships__status=MembershipStatus.APPROVED,
        )

    def pending_memberships(self):
        return CompanyMembership.objects.filter(
            company=self, status__in=(MembershipStatus.REQUESTED, MembershipStatus.INVITED)
        ).select_related("user")

    def request_membership(self, user, *, requested_by=None):
        """Open a membership request from ``user`` (existing company join)."""
        membership, _ = CompanyMembership.objects.get_or_create(
            user=user,
            company=self,
            defaults={
                "status": MembershipStatus.REQUESTED,
                "role": CompanyRole.MEMBER,
                "requested_by": requested_by or user,
            },
        )
        return membership

    def invite_membership(self, user, *, invited_by):
        """Create an administrator-initiated invite (alternative T2 path)."""
        membership, created = CompanyMembership.objects.get_or_create(
            user=user,
            company=self,
            defaults={
                "status": MembershipStatus.INVITED,
                "role": CompanyRole.MEMBER,
                "requested_by": invited_by,
            },
        )
        if created:
            membership.status = MembershipStatus.INVITED
            membership.requested_by = invited_by
            membership.save()
        return membership

    def approve_membership(self, membership, *, reviewed_by):
        """Approve a request/invite; the user then appears as a member."""
        if membership.company_id != self.pk:
            raise ValidationError(_("Cette affiliation appartient à une autre structure."))
        membership.status = MembershipStatus.APPROVED
        membership.reviewed_by = reviewed_by
        membership.reviewed_at = timezone.now()
        membership.save()
        user = membership.user
        if user.company_id != self.pk:
            user.company = self
            user.save(update_fields=["company"])
        return membership

    def decline_membership(self, membership, *, reviewed_by):
        """Decline a pending request or invite (kept in the audit log)."""
        if membership.company_id != self.pk:
            raise ValidationError(_("Cette affiliation appartient à une autre structure."))
        membership.status = MembershipStatus.DECLINED
        membership.reviewed_by = reviewed_by
        membership.reviewed_at = timezone.now()
        membership.save()
        user = membership.user
        if user.company_id == self.pk:
            user.company = None
            user.save(update_fields=["company"])
        return membership


class CompanyMembership(models.Model):
    """
    An affiliation between a user and a company, with an explicit lifecycle.

    T2 security fix: joining an existing company is NEVER implicit. The only
    ways in are (a) the founder's approved membership at creation, (b) a
    request approved by a company administrator, or (c) an administrator's
    invitation accepted by the user. ``reviewed_by`` / ``reviewed_at`` keep
    the validation audit trail; a user only appears as a member once the
    membership is ``approved`` (``User.company`` is the approved company).
    """

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="company_memberships",
        verbose_name=_("utilisateur"),
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name=_("structure"),
    )
    status = models.CharField(
        _("statut"),
        max_length=20,
        choices=MembershipStatus.choices,
        default=MembershipStatus.REQUESTED,
        db_index=True,
    )
    role = models.CharField(
        _("role"),
        max_length=20,
        choices=CompanyRole.choices,
        default=CompanyRole.MEMBER,
    )
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("demandé par"),
    )
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("examiné par"),
    )
    requested_at = models.DateTimeField(_("demandé le"), auto_now_add=True)
    reviewed_at = models.DateTimeField(_("examiné le"), null=True, blank=True)

    class Meta:
        verbose_name = _("affiliation à une structure")
        verbose_name_plural = _("affiliations à une structure")
        ordering = ["-requested_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("user", "company"),
                name="uniq_membership_user_company",
            ),
        ]

    def __str__(self):
        return f"{self.user} → {self.company} ({self.status})"

    @property
    def is_approved(self):
        return self.status == MembershipStatus.APPROVED

    @property
    def is_pending(self):
        return self.status in (MembershipStatus.REQUESTED, MembershipStatus.INVITED)


class UserManager(BaseAuthManager):
    """Standard auth manager (``create_user``/``create_superuser``) on the custom model."""

    use_in_migrations = True


class User(AbstractUser):
    """
    Urban Track user.

    Two account types:
      * ``user`` - the default account for everyone; may publish projects,
        confirm contributions and owns a public portfolio profile;
      * ``admin`` - a privileged account, nominated exclusively by a
        superuser, that can access the admin panel.

    ``professional_id`` is generated at first save and is permanent.
    """

    email = models.EmailField(_("adresse email"), unique=True)
    role = models.CharField(
        _("rôle"),
        max_length=20,
        choices=Role.choices,
        default=Role.USER,
        db_index=True,
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
        verbose_name=_("structure"),
    )
    avatar = models.ImageField(
        _("photo de profil"),
        upload_to="avatars/",
        blank=True,
        help_text=_("Utilisée sur les tableaux de bord et les profils publics."),
    )
    professional_id = models.CharField(
        _("identifiant professionnel"),
        max_length=16,
        unique=True,
        editable=False,
        blank=True,
        help_text=_(
            "Identifiant professionnel unique, gratuit et permanent (OX-XXXXXX). "
            "Attribué à la création, jamais modifié."
        ),
    )
    # Email confirmation: a 6-digit code sent to the email, valid for 24h.
    email_confirmed = models.BooleanField(_("email confirmé"), default=False)
    confirmation_code = models.CharField(
        _("code de confirmation"),
        max_length=10,
        blank=True,
        help_text=_("Code à six chiffres utilisé pour confirmer l'adresse email."),
    )
    confirmation_code_created_at = models.DateTimeField(
        _("code de confirmation créé le"),
        null=True,
        blank=True,
        help_text=_("Utilisé pour faire expirer le code 24 heures après son émission."),
    )
    email_confirmed_at = models.DateTimeField(
        _("email confirmé le"),
        null=True,
        blank=True,
        help_text=_(
            "Date de la confirmation de l'adresse email. Vide tant qu'aucun email "
            "n'a jamais été confirmé : distingue une première inscription d'un "
            "changement d'email en attente."
        ),
    )

    REQUIRED_FIELDS = ["email"]

    objects = UserManager()

    class Meta:
        verbose_name = _("utilisateur")
        verbose_name_plural = _("utilisateurs")

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
    def is_admin_role(self):
        return self.role == Role.ADMIN

    @property
    def is_system_admin(self):
        """Can access the system admin panel (a nominated admin or the superuser)."""
        return self.is_superuser or self.role == Role.ADMIN

    @property
    def is_expert(self):
        """Every regular user is an expert and owns a public portfolio."""
        return self.role == Role.USER

    @property
    def is_company(self):
        """No longer a distinct role — every user belongs to (zeros) a company."""
        return False

    @property
    def is_donor(self):
        """No longer a distinct role."""
        return False

    @property
    def organisation_name(self):
        """Backwards-compatible display name: the linked company, or empty."""
        return self.company.name if self.company else ""

    @property
    def is_company_admin(self):
        """True when the user holds an approved admin role in their company."""
        if not self.company_id:
            return False
        return self.company.is_admin(self)

    @property
    def is_approved_company_member(self):
        """True when the user's linked company is an approved membership (T2)."""
        if not self.company_id:
            return False
        return self.company.is_member(self)

    @property
    def pending_membership(self):
        """
        The first pending (requested/invited) membership, if any.

        Drives the "your company affiliation is awaiting approval" banners.
        """
        return (
            self.company_memberships.filter(
                status__in=(
                    MembershipStatus.REQUESTED,
                    MembershipStatus.INVITED,
                )
            )
            .select_related("company")
            .first()
        )

    @property
    def initials(self):
        """Avatar initials from the name, falling back to the username."""
        parts = f"{self.first_name} {self.last_name}".split()
        if parts:
            return "".join(part[0] for part in parts[:2]).upper()
        cleaned = self.username.replace("@", " ").strip()
        return cleaned[:2].upper() or "?"


class CvTemplate(models.TextChoices):
    """Pluggable CV skins consumed by the cv_generator app (Epic 7)."""

    ACADEMIC_HARVARD_MIT = "academic_harvard_mit", _("Académique (Harvard/MIT)")
    AFD = "afd", _("AFD")
    WORLD_BANK = "world_bank", _("Banque mondiale")


class Skill(models.Model):
    """A professional skill tag attachable to expert portfolios."""

    name = models.CharField(_("nom"), max_length=120, unique=True)

    class Meta:
        verbose_name = _("compétence")
        verbose_name_plural = _("compétences")
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
        verbose_name=_("utilisateur"),
    )
    headline = models.CharField(_("titre / accroche"), max_length=255, blank=True)
    bio = models.TextField(_("biographie"), blank=True)
    city = models.CharField(_("ville"), max_length=120, blank=True)
    country = models.CharField(
        _("pays"),
        max_length=120,
        blank=True,
        help_text=_(
            "Nom du pays au format ISO ; permet un déploiement panafricain puis international."
        ),
    )
    # T4: extended civil-status and CV blocks (all optional, RGPD-friendly).
    nationality = models.CharField(_("nationalité"), max_length=120, blank=True)
    phone = models.CharField(_("téléphone"), max_length=40, blank=True)
    birth_date = models.DateField(
        _("date de naissance"),
        null=True,
        blank=True,
        help_text=_("Facultatif ; conservé confidentiel et jamais affiché sur le site public."),
    )
    strengths = models.JSONField(
        _("points forts"),
        default=list,
        blank=True,
        help_text=_("3 à 5 éléments courts affichés en haut du CV généré."),
    )
    countries_of_intervention = models.JSONField(
        _("pays d'intervention"),
        default=list,
        blank=True,
        help_text=_("Dérivables des projets certifiés ; également modifiables à la main."),
    )
    languages = models.JSONField(
        _("langues"),
        default=list,
        blank=True,
        help_text=_(
            "Une entrée par langue avec trois niveaux distincts, ex. "
            '{"name": "French", "read": "fluent", "write": "fluent", "speak": "native"}'
        ),
    )
    misc = models.TextField(
        _("divers"),
        blank=True,
        help_text=_("Bloc libre court : numéros d'affiliation, certifications…"),
    )
    skills = models.ManyToManyField(
        Skill, blank=True, related_name="experts", verbose_name=_("compétences")
    )
    cv_template = models.CharField(
        _("modèle de CV"),
        max_length=40,
        choices=CvTemplate.choices,
        default=CvTemplate.ACADEMIC_HARVARD_MIT,
        help_text=_("Réservé au générateur de CV."),
    )
    updated_at = models.DateTimeField(_("mis à jour le"), auto_now=True)

    class Meta:
        verbose_name = _("profil d'expert")
        verbose_name_plural = _("profils d'expert")

    def __str__(self):
        return f"Profile of {self.user} ({self.user.professional_id})"

    def get_absolute_url(self):
        """Public URL anchored to the permanent OX-ID (traceability)."""
        from django.urls import reverse

        return reverse("accounts:public_profile", args=[self.user.professional_id])

    def confirmed_contributions(self):
        """Certified experiences only: the public-profile contract."""
        from certification.models import ContributionStatus

        return (
            self.user.contributions.filter(status=ContributionStatus.CONFIRMED)
            .select_related("project", "expert")
            .order_by("-project__duration_start")
        )

    def trust_score(self):
        """
        RG-Score equivalent: certified contributions weighted by role.

        Director 4 / Manager 3 / Specialist 2 / Assistant 1. Defined here in
        Epic 1 so Epic 4's UI and Epic 10's matchmaking share one definition.
        T6 extended the role list; the extra roles default to 1 unless listed.
        """
        weights = {
            "director": 4,
            "manager": 3,
            "specialist": 2,
            "assistant": 1,
            "consultant": 2,
            "engineer": 2,
            "other": 1,
        }
        score = 0
        for contribution in self.confirmed_contributions():
            score += weights.get(contribution.role_type, 1)
        return score

    def synthesis_indicators(self):
        """
        T7: certified synthesis indicators, computed ONLY from confirmed
        contributions (never hand-entered), so they re-calculate on every
        new certification. Shown as the "indicateurs certifiés" block in the
        public profile header and at the top of every CV export.
        """
        from django.utils import timezone

        from certification.models import ContributionStatus

        today = timezone.localdate()
        confirmed = list(
            self.user.contributions.filter(status=ContributionStatus.CONFIRMED).select_related(
                "project", "project__country", "project__funder"
            )
        )
        projects = {c.project_id: c.project for c in confirmed}

        years_experience = 0
        starts = [p.duration_start for p in projects.values() if p.duration_start]
        if starts:
            ends = [p.duration_end for p in projects.values() if p.duration_end]
            latest = max(ends or [], default=None)
            if latest is None:
                latest = today
            years_experience = max(1, (latest - min(starts)).days // 365)

        countries = {p.country.name for p in projects.values() if p.country and p.country.name}
        donor_programmes = {p.id for p in projects.values() if p.funder_id}

        return {
            "years_experience": years_experience,
            "projects": len(projects),
            "contributions": len(confirmed),
            "countries": len(countries),
            "donor_programmes": len(donor_programmes),
        }


class Training(models.Model):
    """A training entry of an expert portfolio (contextual, non-certifying)."""

    profile = models.ForeignKey(
        ExpertProfile,
        on_delete=models.CASCADE,
        related_name="trainings",
        verbose_name=_("profil"),
    )
    title = models.CharField(_("titre"), max_length=255)
    institution = models.CharField(_("établissement"), max_length=255)
    year = models.PositiveIntegerField(_("année"), null=True, blank=True)

    class Meta:
        verbose_name = _("formation")
        verbose_name_plural = _("formations")
        ordering = ["-year", "title"]

    def __str__(self):
        return f"{self.title} ({self.institution})"


class Position(models.Model):
    """
    A professional position (T4a): the backbone of a classic CV.

    Distinct from a project: a position (e.g. heading a research centre since
    2014) is not a project and is never submitted to the project-by-project
    double confirmation. Positions are self-declared and therefore carry the
    "declared, not third-party certified" marker in CV exports (T5 decision).
    """

    profile = models.ForeignKey(
        ExpertProfile,
        on_delete=models.CASCADE,
        related_name="positions",
        verbose_name=_("profil"),
    )
    employer = models.CharField(_("employeur"), max_length=255)
    function = models.CharField(_("fonction"), max_length=255)
    date_start = models.DateField(_("début"))
    date_end = models.DateField(
        _("fin"),
        null=True,
        blank=True,
        help_text=_("Laissez vide pour un poste actuel."),
    )
    description = models.TextField(_("description"), blank=True)

    class Meta:
        verbose_name = _("poste")
        verbose_name_plural = _("postes")
        ordering = ["-date_start"]

    def __str__(self):
        return f"{self.function} — {self.employer}"


class Mandate(models.Model):
    """A professional association membership / mandate (non-certifying)."""

    profile = models.ForeignKey(
        ExpertProfile,
        on_delete=models.CASCADE,
        related_name="mandates",
        verbose_name=_("profil"),
    )
    name = models.CharField(_("association / organisme"), max_length=255)
    role = models.CharField(_("rôle occupé"), max_length=255, blank=True)
    year_start = models.PositiveIntegerField(_("année de début"), null=True, blank=True)
    year_end = models.PositiveIntegerField(_("année de fin"), null=True, blank=True)

    class Meta:
        verbose_name = _("mandat")
        verbose_name_plural = _("mandats")
        ordering = ["-year_start", "name"]

    def __str__(self):
        return f"{self.name} ({self.role})"


class Publication(models.Model):
    """A publication referenced on the portfolio (non-certifying)."""

    profile = models.ForeignKey(
        ExpertProfile,
        on_delete=models.CASCADE,
        related_name="publications",
        verbose_name=_("profil"),
    )
    title = models.CharField(_("titre"), max_length=255)
    venue = models.CharField(
        _("support / revue"),
        max_length=255,
        blank=True,
        help_text=_("Revue, série de rapports, conférence, web…"),
    )
    year = models.PositiveIntegerField(_("année"), null=True, blank=True)

    class Meta:
        verbose_name = _("publication")
        verbose_name_plural = _("publications")
        ordering = ["-year", "title"]

    def __str__(self):
        return f"{self.title} ({self.year})"


class TeachingEntry(models.Model):
    """A teaching activity (course, level, institution, period)."""

    profile = models.ForeignKey(
        ExpertProfile,
        on_delete=models.CASCADE,
        related_name="teaching_entries",
        verbose_name=_("profil"),
    )
    title = models.CharField(_("cours / activité"), max_length=255)
    institution = models.CharField(_("établissement"), max_length=255, blank=True)
    year = models.PositiveIntegerField(_("année"), null=True, blank=True)

    class Meta:
        verbose_name = _("activité d'enseignement")
        verbose_name_plural = _("activités d'enseignement")
        ordering = ["-year", "title"]

    def __str__(self):
        return f"{self.title} ({self.institution})"


class MediaAppearance(models.Model):
    """A media appearance (title, outlet, date, link)."""

    profile = models.ForeignKey(
        ExpertProfile,
        on_delete=models.CASCADE,
        related_name="media_appearances",
        verbose_name=_("profil"),
    )
    title = models.CharField(_("titre"), max_length=255)
    outlet = models.CharField(_("média / support"), max_length=255, blank=True)
    year = models.PositiveIntegerField(_("année"), null=True, blank=True)
    url = models.URLField(_("URL"), max_length=500, blank=True)

    class Meta:
        verbose_name = _("apparition médiatique")
        verbose_name_plural = _("apparitions médiatiques")
        ordering = ["-year", "title"]

    def __str__(self):
        return f"{self.title} ({self.outlet})"
