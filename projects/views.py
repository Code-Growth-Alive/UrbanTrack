"""
Project views: public directory, public detail, company publishing flow
(create draft -> declare contributors -> publish -> archive) and the
company side of the adjustment validation cycle (rule 4).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView, ListView

from accounts.models import User
from certification.models import (
    ConfirmationSource,
    ContributionStatus,
    ProjectContribution,
)
from certification.services import (
    CertificationError,
    approve_adjustment,
    declare_contributor,
    notify_contribution,
    request_client_confirmation,
)
from projects.services import PublishingError, archive_project, publish_project

from .forms import (
    DeclareContributorForm,
    ProjectForm,
    ProjectLinkForm,
    ProjectMediaForm,
    RequestClientConfirmationForm,
)
from .models import (
    Project,
    ProjectLink,
    ProjectMedia,
    ProjectPhase,
    ProjectStatus,
    ProjectVisibility,
)


class ProjectListView(ListView):
    """Public directory: published + public projects only (T6 filters)."""

    model = Project
    context_object_name = "projects"
    template_name = "projects/list.html"
    paginate_by = 12

    def get_queryset(self):
        from django.db.models import Q

        qs = (
            Project.objects.filter(
                status=ProjectStatus.PUBLISHED,
                visibility=ProjectVisibility.PUBLIC,
            )
            .select_related("published_by", "client", "country", "funder")
            .prefetch_related("contributions", "tags")
        )
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(official_name__icontains=q)
                | Q(client_name__icontains=q)
                | Q(client__name__icontains=q)
                | Q(description__icontains=q)
                | Q(deliverables__icontains=q)
                | Q(country__name__icontains=q)
                | Q(funder__name__icontains=q)
                | Q(tags__name__icontains=q)
            )
        country = (self.request.GET.get("country") or "").strip()
        if country:
            qs = qs.filter(country__name__iexact=country)
        client = (self.request.GET.get("client") or "").strip()
        if client:
            qs = qs.filter(client__name__iexact=client)
        funder = (self.request.GET.get("funder") or "").strip()
        if funder:
            qs = qs.filter(funder__name__iexact=funder)
        phase = (self.request.GET.get("phase") or "").strip()
        if phase in ProjectPhase.values:
            qs = qs.filter(phase=phase)
        tag = (self.request.GET.get("tag") or "").strip()
        if tag:
            qs = qs.filter(tags__name__iexact=tag)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["query"] = (self.request.GET.get("q") or "").strip()
        ctx["filter_country"] = (self.request.GET.get("country") or "").strip()
        ctx["filter_client"] = (self.request.GET.get("client") or "").strip()
        ctx["filter_funder"] = (self.request.GET.get("funder") or "").strip()
        ctx["filter_phase"] = (self.request.GET.get("phase") or "").strip()
        ctx["filter_tag"] = (self.request.GET.get("tag") or "").strip()
        ctx["countries"] = (
            Project.objects.filter(
                status=ProjectStatus.PUBLISHED,
                visibility=ProjectVisibility.PUBLIC,
                country__isnull=False,
            )
            .order_by("country__name")
            .values_list("country__name", flat=True)
            .distinct()
        )
        ctx["funders"] = (
            Project.objects.filter(
                status=ProjectStatus.PUBLISHED,
                visibility=ProjectVisibility.PUBLIC,
                funder__isnull=False,
            )
            .order_by("funder__name")
            .values_list("funder__name", flat=True)
            .distinct()
        )
        ctx["clients"] = (
            Project.objects.filter(
                status=ProjectStatus.PUBLISHED,
                visibility=ProjectVisibility.PUBLIC,
                client__isnull=False,
            )
            .order_by("client__name")
            .values_list("client__name", flat=True)
            .distinct()
        )
        ctx["phases"] = ProjectPhase.choices
        return ctx


class ProjectPublicDetailView(DetailView):
    """
    Public proof page of a project.

    T3 traceability fix: certified contributions must stay verifiable by a
    third party, so the page is always reachable once the project has a
    confirmed contributor:

      * ``published`` + ``public`` projects render the full page;
      * private, draft or archived projects with at least one certified
        contribution render a MINIMAL public page — official name, client,
        dates and certified contributors only. The rest of the content
        (description, deliverables, media, references) never leaks;
      * a project with no certified contribution ever is not public at all.
    """

    model = Project
    template_name = "projects/project_detail.html"
    context_object_name = "project"

    def get_object(self, queryset=None):
        project = get_object_or_404(
            Project.objects.select_related("published_by"),
            pk=self.kwargs["pk"],
        )
        if project.is_publicly_visible:
            return project
        if project.confirmed_contributions().exists():
            return project
        raise Http404(_("Aucun projet n'est disponible à cette adresse."))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Minimal page = certified history exists but the project is not (or
        # no longer) fully public: only the certificate facts are exposed.
        context["is_minimal"] = not self.object.is_publicly_visible
        context["confirmed_contributions"] = self.object.confirmed_contributions().select_related(
            "expert", "project"
        )
        context["images"] = self.object.media_items.filter(kind=ProjectMedia.MediaKind.IMAGE)
        context["documents"] = self.object.media_items.filter(kind=ProjectMedia.MediaKind.DOCUMENT)
        context["seo_title"] = f"{self.object.official_name} : Urban Track"
        context["seo_description"] = (
            _(
                "Page de preuve de certification : un projet certifié par double "
                "confirmation, avec ses contributeurs vérifiés."
            )
            if context["is_minimal"]
            else (self.object.description or self.object.official_name)
        )
        first_image = context["images"].first()
        context["seo_image"] = self.request.build_absolute_uri(
            first_image.file.url if first_image else static("img/hero-facade.jpg")
        )
        context["seo_url"] = self.request.build_absolute_uri(self.object.get_absolute_url())
        return context


def _owned_project_or_403(request, pk):
    project = get_object_or_404(Project.objects.select_related("published_by"), pk=pk)
    if project.published_by_id != request.user.pk and not request.user.is_superuser:
        raise PermissionDenied(_("Seule la structure qui a publié ce projet peut le gérer."))
    return project


@login_required
def project_create(request):
    """Publish a new project (draft first) — every user can publish."""
    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.published_by = request.user
            project.status = ProjectStatus.DRAFT
            project.save()
            form.save_m2m()  # thematic tags (T6)
            messages.success(
                request,
                _("Brouillon enregistré : déclarez maintenant les experts qui ont contribué."),
            )
            return redirect("projects:manage", pk=project.pk)
    else:
        form = ProjectForm()
    return render(request, "projects/form.html", {"form": form})


@login_required
def project_edit(request, pk):
    """Owner edits the core fields of a project (draft or published)."""
    project = _owned_project_or_403(request, pk)

    if request.method == "POST":
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            messages.success(request, _("Projet mis à jour."))
            return redirect("projects:manage", pk=project.pk)
    else:
        form = ProjectForm(instance=project)
    return render(
        request,
        "projects/form.html",
        {"form": form, "project": project, "editing": True},
    )


@require_http_methods(["POST"])
@login_required
def project_delete(request, pk):
    """Owner deletes a draft project (published projects keep their certificate history)."""
    project = _owned_project_or_403(request, pk)
    if project.status == ProjectStatus.PUBLISHED:
        messages.error(
            request,
            _(
                "Ce projet est publié et ses contributions certifiées doivent être "
                "préservées. Archivez-le au lieu de le supprimer."
            ),
        )
        return redirect("projects:manage", pk=project.pk)
    official_name = project.official_name
    project.delete()
    messages.success(
        request,
        _("Brouillon de projet « %(name)s » supprimé.") % {"name": official_name},
    )
    return redirect("accounts:dashboard")


@login_required
def project_manage(request, pk):
    """
    Company workspace for one project: declare contributors, publish,
    archive, adjust visibility while drafting, and validate expert-adjusted
    wordings (rule 4). Every action posts back here.
    """
    project = _owned_project_or_403(request, pk)
    contributions = project.contributions.select_related("expert").order_by("id")
    bound_form = None

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "declare":
                bound_form = DeclareContributorForm(request.POST)
                if bound_form.is_valid():
                    contribution = declare_contributor(
                        project,
                        email=bound_form.cleaned_data["email"],
                        role_type=bound_form.cleaned_data["role_type"],
                        contribution_bullets=bound_form.cleaned_data["contribution_bullets"],
                        added_by=request.user,
                        confirmation_source=bound_form.cleaned_data["confirmation_source"],
                    )
                    # Draft stage: invitation goes out at publish time.
                    # On a published project the expert is contacted now.
                    if project.status == ProjectStatus.PUBLISHED:
                        notify_contribution(contribution)
                    messages.success(
                        request,
                        _("Contributeur déclaré sur le projet."),
                    )
                    return redirect("projects:manage", pk=project.pk)
            elif action == "request_client_confirmation":
                client_form = RequestClientConfirmationForm(request.POST)
                if client_form.is_valid():
                    contribution = get_object_or_404(
                        ProjectContribution,
                        pk=client_form.cleaned_data["contribution_pk"],
                        project=project,
                    )
                    request_client_confirmation(
                        contribution,
                        request.user,
                        client_email=client_form.cleaned_data["client_email"],
                    )
                    messages.success(
                        request,
                        _(
                            "Un lien de confirmation a été envoyé par e-mail au "
                            "client / maître d'ouvrage."
                        ),
                    )
                    return redirect("projects:manage", pk=project.pk)
                for error in client_form.errors.values():
                    messages.error(request, " ".join(error))
            elif action == "publish":
                publish_project(project)
                messages.success(
                    request,
                    _("Projet publié : les invitations ont été envoyées à chaque expert déclaré."),
                )
                return redirect("projects:manage", pk=project.pk)
            elif action == "archive":
                archive_project(project)
                messages.success(request, _("Projet archivé."))
                return redirect("projects:manage", pk=project.pk)
            elif action == "visibility":
                if project.status == ProjectStatus.DRAFT:
                    requested = request.POST.get("visibility")
                    if requested in ProjectVisibility.values:
                        project.visibility = requested
                        project.save(update_fields=["visibility", "updated_at"])
                        messages.success(request, _("Visibilité du projet mise à jour."))
                return redirect("projects:manage", pk=project.pk)
            elif action == "add_link":
                link_form = ProjectLinkForm(request.POST)
                if link_form.is_valid():
                    ProjectLink.objects.create(
                        project=project,
                        label=link_form.cleaned_data["label"],
                        url=link_form.cleaned_data["url"],
                    )
                    messages.success(request, _("Lien ajouté au projet."))
                    return redirect("projects:manage", pk=project.pk)
                for error in link_form.errors.values():
                    messages.error(request, " ".join(error))
            elif action == "delete_link":
                get_object_or_404(
                    ProjectLink, pk=request.POST.get("link_pk"), project=project
                ).delete()
                messages.success(request, _("Lien supprimé."))
            elif action == "add_media":
                media_form = ProjectMediaForm(request.POST, request.FILES)
                if media_form.is_valid():
                    item = ProjectMedia(
                        project=project,
                        kind=media_form.cleaned_data["kind"],
                        caption=media_form.cleaned_data.get("caption", ""),
                        file=media_form.cleaned_data["file"],
                    )
                    try:
                        item.full_clean()
                    except ValidationError as ve:
                        messages.error(request, " ".join(ve.messages))
                        return redirect("projects:manage", pk=project.pk)
                    item.save()
                    messages.success(request, _("Média ajouté au projet."))
                    return redirect("projects:manage", pk=project.pk)
                for error in media_form.errors.values():
                    messages.error(request, " ".join(error))
            elif action == "delete_media":
                get_object_or_404(
                    ProjectMedia, pk=request.POST.get("media_pk"), project=project
                ).delete()
                messages.success(request, _("Média supprimé."))
            elif action == "approve":
                contribution = get_object_or_404(
                    ProjectContribution,
                    pk=request.POST.get("contribution_pk"),
                    project=project,
                )
                approve_adjustment(contribution, request.user)
                messages.success(
                    request,
                    _("Reformulation validée : l'expérience est certifiée."),
                )
                return redirect("projects:manage", pk=project.pk)
        except (ValidationError, CertificationError, PublishingError) as error:
            flat = getattr(error, "message_dict", None)
            text = (
                "; ".join(msg for msgs in flat.values() for msg in msgs)
                if isinstance(flat, dict)
                else str(error)
            )
            messages.error(request, text)
            return redirect("projects:manage", pk=project.pk)

    form = bound_form or DeclareContributorForm()
    link_form = ProjectLinkForm()
    media_form = ProjectMediaForm()
    client_form = RequestClientConfirmationForm()

    existing_experts = User.objects.filter(email_confirmed=True).order_by("-date_joined")[:200]
    return render(
        request,
        "projects/manage.html",
        {
            "project": project,
            "contributions": contributions,
            "form": form,
            "existing_experts": existing_experts,
            "link_form": link_form,
            "media_form": media_form,
            "client_form": client_form,
            "confirmation_source_client": ConfirmationSource.CLIENT,
            "status_draft": ProjectStatus.DRAFT,
            "status_published": ProjectStatus.PUBLISHED,
            "status_pending_confirmation": ContributionStatus.PENDING_CONFIRMATION,
        },
    )
