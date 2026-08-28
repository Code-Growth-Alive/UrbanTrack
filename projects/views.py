"""
Project views: public directory, public detail, company publishing flow
(create draft -> declare contributors -> publish -> archive) and the
company side of the adjustment validation cycle (rule 4).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView, ListView

from accounts.models import Role, User
from certification.models import ContributionStatus, ProjectContribution
from certification.services import (
    CertificationError,
    approve_adjustment,
    declare_contributor,
    notify_contribution,
)
from projects.services import PublishingError, archive_project, publish_project

from .forms import (
    DeclareContributorForm,
    ProjectForm,
    ProjectLinkForm,
    ProjectMediaForm,
)
from .models import (
    Project,
    ProjectLink,
    ProjectMedia,
    ProjectStatus,
    ProjectVisibility,
)


class ProjectListView(ListView):
    """Public directory: published + public projects only."""

    model = Project
    context_object_name = "projects"
    template_name = "projects/list.html"
    paginate_by = 12

    def get_queryset(self):
        qs = (
            Project.objects.filter(
                status=ProjectStatus.PUBLISHED,
                visibility=ProjectVisibility.PUBLIC,
            )
            .select_related("published_by")
            .prefetch_related("contributions")
        )
        q = (self.request.GET.get("q") or "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(
                Q(official_name__icontains=q)
                | Q(client_name__icontains=q)
                | Q(description__icontains=q)
                | Q(deliverables__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["query"] = (self.request.GET.get("q") or "").strip()
        return ctx


class ProjectPublicDetailView(DetailView):
    model = Project
    template_name = "projects/project_detail.html"
    context_object_name = "project"

    def get_queryset(self):
        return Project.objects.filter(
            status=ProjectStatus.PUBLISHED,
            visibility=ProjectVisibility.PUBLIC,
        ).select_related("published_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["confirmed_contributions"] = self.object.confirmed_contributions().select_related(
            "expert", "project"
        )
        context["images"] = self.object.media_items.filter(kind=ProjectMedia.MediaKind.IMAGE)
        context["documents"] = self.object.media_items.filter(kind=ProjectMedia.MediaKind.DOCUMENT)
        context["videos"] = self.object.media_items.filter(kind=ProjectMedia.MediaKind.VIDEO)
        return context


def _owned_project_or_403(request, pk):
    project = get_object_or_404(Project.objects.select_related("published_by"), pk=pk)
    if project.published_by_id != request.user.pk and not request.user.is_superuser:
        raise PermissionDenied(_("Only the publishing company can manage this project."))
    return project


@login_required
def project_create(request):
    """Epic 2 entry point: publish a new project (draft first)."""
    if not (request.user.is_company or request.user.is_donor or request.user.is_superuser):
        raise PermissionDenied(_("Only company accounts can publish projects."))

    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.published_by = request.user
            project.status = ProjectStatus.DRAFT
            project.save()
            messages.success(
                request,
                _("Draft saved: now declare the experts who contributed."),
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
            messages.success(request, _("Project updated."))
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
                "This project is published and its certified contributions must be "
                "preserved. Archive it instead of deleting."
            ),
        )
        return redirect("projects:manage", pk=project.pk)
    official_name = project.official_name
    project.delete()
    messages.success(request, _("Draft project “%(name)s” deleted.") % {"name": official_name})
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
                    )
                    # Draft stage: invitation goes out at publish time.
                    # On a published project the expert is contacted now.
                    if project.status == ProjectStatus.PUBLISHED:
                        notify_contribution(contribution)
                    messages.success(
                        request,
                        _("Contributor declared on the project."),
                    )
                    return redirect("projects:manage", pk=project.pk)
            elif action == "publish":
                publish_project(project)
                messages.success(
                    request,
                    _(
                        "Project published: invitations have been dispatched "
                        "to every declared expert."
                    ),
                )
                return redirect("projects:manage", pk=project.pk)
            elif action == "archive":
                archive_project(project)
                messages.success(request, _("Project archived."))
                return redirect("projects:manage", pk=project.pk)
            elif action == "visibility":
                if project.status == ProjectStatus.DRAFT:
                    requested = request.POST.get("visibility")
                    if requested in ProjectVisibility.values:
                        project.visibility = requested
                        project.save(update_fields=["visibility", "updated_at"])
                        messages.success(request, _("Project visibility updated."))
                return redirect("projects:manage", pk=project.pk)
            elif action == "add_link":
                link_form = ProjectLinkForm(request.POST)
                if link_form.is_valid():
                    ProjectLink.objects.create(
                        project=project,
                        label=link_form.cleaned_data["label"],
                        url=link_form.cleaned_data["url"],
                    )
                    messages.success(request, _("Link attached to the project."))
                    return redirect("projects:manage", pk=project.pk)
                for error in link_form.errors.values():
                    messages.error(request, " ".join(error))
            elif action == "delete_link":
                get_object_or_404(
                    ProjectLink, pk=request.POST.get("link_pk"), project=project
                ).delete()
                messages.success(request, _("Link removed."))
            elif action == "add_media":
                media_form = ProjectMediaForm(request.POST, request.FILES)
                if media_form.is_valid():
                    item = ProjectMedia(
                        project=project,
                        kind=media_form.cleaned_data["kind"],
                        caption=media_form.cleaned_data.get("caption", ""),
                        url=media_form.cleaned_data.get("url", ""),
                    )
                    if media_form.cleaned_data["file"]:
                        item.file = media_form.cleaned_data["file"]
                    try:
                        item.full_clean()
                    except ValidationError as ve:
                        messages.error(request, " ".join(ve.messages))
                        return redirect("projects:manage", pk=project.pk)
                    item.save()
                    messages.success(request, _("Media attached to the project."))
                    return redirect("projects:manage", pk=project.pk)
                for error in media_form.errors.values():
                    messages.error(request, " ".join(error))
            elif action == "delete_media":
                get_object_or_404(
                    ProjectMedia, pk=request.POST.get("media_pk"), project=project
                ).delete()
                messages.success(request, _("Media removed."))
            elif action == "approve":
                contribution = get_object_or_404(
                    ProjectContribution,
                    pk=request.POST.get("contribution_pk"),
                    project=project,
                )
                approve_adjustment(contribution, request.user)
                messages.success(
                    request,
                    _("Adjusted wording validated: the experience is certified."),
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

    existing_experts = User.objects.filter(role=Role.EXPERT).order_by("-date_joined")[:200]
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
            "status_draft": ProjectStatus.DRAFT,
            "status_published": ProjectStatus.PUBLISHED,
            "status_pending_confirmation": ContributionStatus.PENDING_CONFIRMATION,
        },
    )
