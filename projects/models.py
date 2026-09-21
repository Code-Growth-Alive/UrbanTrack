"""
Project model: a real-world urban development project published by a company.

This is the Urban Track equivalent of a ResearchGate "claimed publication":
the company that carried out the project publishes it and declares the
experts who contributed (see certification.ProjectContribution).
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class ProjectStatus(models.TextChoices):
    DRAFT = "draft", _("Brouillon")
    PUBLISHED = "published", _("Publié")
    ARCHIVED = "archived", _("Archivé")


class ProjectVisibility(models.TextChoices):
    PUBLIC = "public", _("Public")
    PRIVATE = "private", _("Privé")


class ProjectPhase(models.TextChoices):
    """Business status of a project (en cours / achevé), T6."""

    ONGOING = "ongoing", _("En cours")
    COMPLETED = "completed", _("Terminé")


class VolumeUnit(models.TextChoices):
    """Donor-format intervention volumes (T6), distinct from the budget."""

    PERSON_DAYS = "person_days", _("jours-personnes")
    PERSON_MONTHS = "person_months", _("mois-personnes")


class Country(models.Model):
    """Structured country referential (T6): the domain of a project."""

    name = models.CharField(_("nom"), max_length=120, unique=True)
    iso3 = models.CharField(
        _("ISO 3166-1 alpha-3"),
        max_length=3,
        blank=True,
        unique=True,
        null=True,
    )

    class Meta:
        verbose_name = _("pays")
        verbose_name_plural = _("pays")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.iso3:
            self.iso3 = self.iso3.strip().upper()
            if len(self.iso3) != 3:
                raise ValidationError(
                    {"iso3": _("Le code ISO doit comporter exactement 3 lettres.")}
                )


class Funder(models.Model):
    """Structured funder referential (T6), distinct from the maître d'ouvrage
    (``client_name``): who finances the project vs who commissioned it."""

    name = models.CharField(_("nom"), max_length=160, unique=True)

    class Meta:
        verbose_name = _("bailleur")
        verbose_name_plural = _("bailleurs")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Client(models.Model):
    """Structured client / maître d'ouvrage referential (T9)."""

    name = models.CharField(_("nom"), max_length=160, unique=True)

    class Meta:
        verbose_name = _("client")
        verbose_name_plural = _("clients")
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProjectTag(models.Model):
    """Thematic keyword, shared across projects for filtering (T6)."""

    name = models.CharField(_("nom"), max_length=60, unique=True)

    class Meta:
        verbose_name = _("mot-clé de projet")
        verbose_name_plural = _("mots-clés de projet")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Project(models.Model):
    """
    A project carried out by a company, published to certify expert contributions.

    Lifecycle: ``draft`` -> ``published`` -> ``archived``. Publishing is what
    triggers the cross-confirmation invitations (certification app). Only
    ``published`` + ``public`` projects appear in the public directory; the
    full detail page is served for them. Private/draft/archived projects with
    a certified contribution are still reachable through a MINIMAL public
    proof page (name, client, dates, certified contributors) so the "traceable
    to the project page" guarantee stays real (T3).

    Field names follow the mandated data model (spec section 4). Two
    additive fields were required by the business logic and are flagged as
    deviations-by-addition in the README: ``published_by`` (ownership of the
    publishing company user) and timestamps.
    """

    official_name = models.CharField(_("nom officiel"), max_length=255)
    description = models.TextField(_("description"))
    deliverables = models.TextField(
        _("livrables"),
        help_text=_("Un livrable par ligne."),
    )
    duration_start = models.DateField(_("date de début"))
    duration_end = models.DateField(
        _("date de fin"),
        null=True,
        blank=True,
        help_text=_("Laissez vide pour un projet en cours."),
    )
    # T6: donor-format enrichment (all optional, structured).
    country = models.ForeignKey(
        Country,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects",
        verbose_name=_("pays"),
        help_text=_("Pays d'intervention structuré ; saisissez un nom et il est réutilisé."),
    )
    funder = models.ForeignKey(
        Funder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects",
        verbose_name=_("bailleur"),
        help_text=_(
            "Bailleur, distinct du maître d'ouvrage : qui finance le projet "
            "plutôt que qui l'a commandé."
        ),
    )
    phase = models.CharField(
        _("phase"),
        max_length=20,
        choices=ProjectPhase.choices,
        default=ProjectPhase.ONGOING,
        help_text=_("Statut du projet : en cours ou achevé."),
    )
    intervention_volume = models.PositiveIntegerField(
        _("volume d'intervention"),
        null=True,
        blank=True,
        help_text=_("Le volume d'intervention, dans l'unité choisie ci-dessous."),
    )
    volume_unit = models.CharField(
        _("unité de volume"),
        max_length=20,
        choices=VolumeUnit.choices,
        null=True,
        blank=True,
    )
    personal_start = models.DateField(
        _("début de la participation personnelle"),
        null=True,
        blank=True,
        help_text=_(
            "Début de VOTRE participation personnelle "
            "(sous-ensemble de la durée du projet)."
        ),
    )
    personal_end = models.DateField(
        _("fin de la participation personnelle"),
        null=True,
        blank=True,
        help_text=_("Laissez vide si votre participation est toujours en cours."),
    )
    tags = models.ManyToManyField(
        ProjectTag,
        blank=True,
        related_name="projects",
        verbose_name=_("mots-clés thématiques"),
        help_text=_(
            "Mots-clés thématiques séparés par des virgules ; "
            "réutilisés sur plusieurs projets."
        ),
    )
    budget = models.DecimalField(
        _("budget"), max_digits=16, decimal_places=2, null=True, blank=True
    )
    client_name = models.CharField(_("nom du client"), max_length=255)
    client = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects",
        verbose_name=_("client"),
        help_text=_(
            "Client / maître d'ouvrage structuré ; réutilisé pour une "
            "recherche et des filtres cohérents."
        ),
    )
    status = models.CharField(
        _("statut"),
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.DRAFT,
        db_index=True,
    )
    visibility = models.CharField(
        _("visibilité"),
        max_length=20,
        choices=ProjectVisibility.choices,
        default=ProjectVisibility.PRIVATE,
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="published_projects",
        verbose_name=_("publié par"),
    )
    created_at = models.DateTimeField(_("créé le"), auto_now_add=True)
    updated_at = models.DateTimeField(_("modifié le"), auto_now=True)

    class Meta:
        verbose_name = _("projet")
        verbose_name_plural = _("projets")
        ordering = ["-duration_start", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(duration_end__gte=models.F("duration_start"))
                | models.Q(duration_end__isnull=True),
                name="project_duration_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(personal_end__gte=models.F("personal_start"))
                | models.Q(personal_end__isnull=True)
                | models.Q(personal_start__isnull=True),
                name="project_personal_end_after_start",
            ),
        ]

    def __str__(self):
        return self.official_name

    def save(self, *args, **kwargs):
        if self.client and self.client_name != self.client.name:
            self.client_name = self.client.name
        elif self.client_name and not self.client_id:
            self.client = Client.objects.filter(name__iexact=self.client_name.strip()).first()
            if self.client:
                self.client_name = self.client.name
        super().save(*args, **kwargs)

    def clean(self):
        if self.duration_start and self.duration_end and self.duration_end < self.duration_start:
            raise ValidationError(
                {"duration_end": _("La date de fin doit être postérieure à la date de début.")}
            )
        if (
            self.personal_start
            and self.personal_end
            and self.personal_end < self.personal_start
        ):
            raise ValidationError(
                {
                    "personal_end": _(
                        "La date de fin de la participation personnelle doit être "
                        "postérieure à sa date de début."
                    )
                }
            )

    @property
    def volume_label(self):
        """Human label for the intervention volume, e.g. "12 person-months"."""
        if not self.intervention_volume:
            return ""
        unit = self.get_volume_unit_display() if self.volume_unit else ""
        return f"{self.intervention_volume} {unit}".strip()

    @property
    def personal_period_label(self):
        """Label for the personal participation window, e.g. "03/2023 – 12/2024"."""
        if not self.personal_start:
            return ""
        start = self.personal_start.strftime("%m/%Y")
        if not self.personal_end:
            return f"{start} – …"
        return f"{start} – {self.personal_end.strftime('%m/%Y')}"

    def get_absolute_url(self):
        return reverse("projects:detail", args=[self.pk])

    @property
    def deliverables_lines(self):
        """Deliverables as a list: one per line in the stored text."""
        return [line.strip() for line in self.deliverables.splitlines() if line.strip()]

    @property
    def is_publicly_visible(self):
        """True only when published AND public: the public-site gate."""
        return (
            self.status == ProjectStatus.PUBLISHED and self.visibility == ProjectVisibility.PUBLIC
        )

    def confirmed_contributions(self):
        """Contributions certified by independent double confirmation."""
        from certification.models import ContributionStatus

        return self.contributions.filter(status=ContributionStatus.CONFIRMED).select_related(
            "expert"
        )


class ProjectLink(models.Model):
    """An external reference (news article, official page, report…) on a project."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="links")
    label = models.CharField(_("libellé"), max_length=120)
    url = models.URLField(_("URL"), max_length=500)
    created_at = models.DateTimeField(_("créé le"), auto_now_add=True)

    class Meta:
        verbose_name = _("lien de projet")
        verbose_name_plural = _("liens de projet")
        ordering = ["id"]

    def __str__(self):
        return self.label


class ProjectMedia(models.Model):
    """
    Optional media attached to a project: an uploaded image or document.
    Everything is optional by design.
    """

    class MediaKind(models.TextChoices):
        IMAGE = "image", _("Image")
        DOCUMENT = "document", _("Document")

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="media_items")
    kind = models.CharField(_("type"), max_length=20, choices=MediaKind.choices)
    file = models.FileField(
        _("fichier"),
        upload_to="project_media/%Y/%m/",
        blank=True,
        help_text=_("Utilisé pour les images et les documents."),
    )
    caption = models.CharField(_("légende"), max_length=200, blank=True)
    uploaded_at = models.DateTimeField(_("ajouté le"), auto_now_add=True)

    class Meta:
        verbose_name = _("média de projet")
        verbose_name_plural = _("médias de projet")
        ordering = ["id"]

    def __str__(self):
        return self.caption or self.get_kind_display()

    def clean(self):
        if not self.file:
            raise ValidationError({"file": _("Un fichier doit être fourni.")})
