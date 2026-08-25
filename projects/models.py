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
    DRAFT = "draft", _("Draft")
    PUBLISHED = "published", _("Published")
    ARCHIVED = "archived", _("Archived")


class ProjectVisibility(models.TextChoices):
    PUBLIC = "public", _("Public")
    PRIVATE = "private", _("Private")


class Project(models.Model):
    """
    A project carried out by a company, published to certify expert contributions.

    Lifecycle: ``draft`` -> ``published`` -> ``archived``. Publishing is what
    triggers the cross-confirmation invitations (certification app). Only
    ``published`` + ``public`` projects are reachable on the public site.

    Field names follow the mandated data model (spec section 4). Two
    additive fields were required by the business logic and are flagged as
    deviations-by-addition in the README: ``published_by`` (ownership of the
    publishing company user) and timestamps.
    """

    official_name = models.CharField(_("official name"), max_length=255)
    description = models.TextField(_("description"))
    deliverables = models.TextField(
        _("deliverables"),
        help_text=_("One deliverable per line."),
    )
    duration_start = models.DateField(_("duration start"))
    duration_end = models.DateField(
        _("duration end"), null=True, blank=True,
        help_text=_("Leave empty for an ongoing project."),
    )
    budget = models.DecimalField(
        _("budget"), max_digits=16, decimal_places=2, null=True, blank=True
    )
    client_name = models.CharField(_("client name"), max_length=255)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.DRAFT,
        db_index=True,
    )
    visibility = models.CharField(
        _("visibility"),
        max_length=20,
        choices=ProjectVisibility.choices,
        default=ProjectVisibility.PRIVATE,
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="published_projects",
        limit_choices_to={"role": "company"},
        verbose_name=_("published by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("project")
        verbose_name_plural = _("projects")
        ordering = ["-duration_start", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(duration_end__gte=models.F("duration_start"))
                | models.Q(duration_end__isnull=True),
                name="project_duration_end_after_start",
            ),
        ]

    def __str__(self):
        return self.official_name

    def clean(self):
        if (
            self.duration_start
            and self.duration_end
            and self.duration_end < self.duration_start
        ):
            raise ValidationError(
                {"duration_end": _("The end date must be after the start date.")}
            )

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
            self.status == ProjectStatus.PUBLISHED
            and self.visibility == ProjectVisibility.PUBLIC
        )

    def confirmed_contributions(self):
        """Contributions certified by independent double confirmation."""
        from certification.models import ContributionStatus

        return self.contributions.filter(status=ContributionStatus.CONFIRMED).select_related(
            "expert"
        )


class ProjectLink(models.Model):
    """An external reference (news article, official page, report…) on a project."""

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="links"
    )
    label = models.CharField(_("label"), max_length=120)
    url = models.URLField(_("URL"), max_length=500)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("project link")
        verbose_name_plural = _("project links")
        ordering = ["id"]

    def __str__(self):
        return self.label


class ProjectMedia(models.Model):
    """
    Optional media attached to a project: uploaded image/document or an
    embedded video URL (YouTube). Everything is optional by design.
    """

    class MediaKind(models.TextChoices):
        IMAGE = "image", _("Image")
        DOCUMENT = "document", _("Document")
        VIDEO = "video", _("Video")

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="media_items"
    )
    kind = models.CharField(_("kind"), max_length=20, choices=MediaKind.choices)
    file = models.FileField(
        _("file"),
        upload_to="project_media/%Y/%m/",
        blank=True,
        help_text=_("Used for images and documents."),
    )
    url = models.URLField(
        _("video URL"),
        max_length=500,
        blank=True,
        help_text=_("Used for embedded videos (YouTube)."),
    )
    caption = models.CharField(_("caption"), max_length=200, blank=True)
    uploaded_at = models.DateTimeField(_("uploaded at"), auto_now_add=True)

    class Meta:
        verbose_name = _("project media")
        verbose_name_plural = _("project media")
        ordering = ["id"]

    def __str__(self):
        return self.caption or self.get_kind_display()

    def clean(self):
        if self.kind in (self.MediaKind.IMAGE, self.MediaKind.DOCUMENT) and not self.file:
            raise ValidationError({"file": _("An uploaded file is required.")})
        if self.kind == self.MediaKind.VIDEO and not self.url:
            raise ValidationError({"url": _("A video URL is required.")})

    @property
    def embed_url(self):
        """Normalise common YouTube URL shapes into an embeddable src."""
        from urllib.parse import parse_qs, urlparse

        if not self.url:
            return ""
        parsed = urlparse(self.url)
        host = parsed.netloc.lower().removeprefix("www.")
        if host == "youtu.be":
            return f"https://www.youtube.com/embed{parsed.path}"
        if host in ("youtube.com", "m.youtube.com"):
            if parsed.path.startswith("/embed/"):
                return self.url
            if parsed.path.startswith("/shorts/"):
                video_id = parsed.path.removeprefix("/shorts/").split("/")[0]
                return f"https://www.youtube.com/embed/{video_id}"
            if parsed.path == "/watch":
                video_id = parse_qs(parsed.query).get("v", [""])[0]
                if video_id:
                    return f"https://www.youtube.com/embed/{video_id}"
            return self.url
        return self.url
