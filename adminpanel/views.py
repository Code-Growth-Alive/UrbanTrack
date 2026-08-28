"""
System admin dashboard: cross-app operational overview and management of
users, jobs, projects and applications. Restricted to staff/superusers and
separate from the Django admin panel (which remains the deep edit surface).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from accounts.models import Role, User
from certification.models import ContributionStatus, ProjectContribution
from jobs.models import ApplicationStatus, Job, JobApplication, JobStatus
from projects.models import Project, ProjectStatus

from .forms import AdminUserForm


def _require_system_admin(view):
    """Login + staff/superuser gate shared by every admin-panel route."""
    return login_required(view)


def is_system_admin(user):
    return bool(getattr(user, "is_authenticated", False)) and (
        user.is_superuser or user.is_staff
    )


@_require_system_admin
def admin_dashboard(request):
    """Operational overview: key counts + recent items per domain."""
    if not is_system_admin(request.user):
        raise PermissionDenied(_("Only system administrators can access this page."))

    by_role = (
        User.objects.values("role").annotate(count=Count("id")).order_by("role")
    )
    role_counts = {row["role"]: row["count"] for row in by_role}
    role_counts["total"] = sum(role_counts.values())

    disputed = ProjectContribution.objects.filter(status=ContributionStatus.DISPUTED).count()

    context = {
        "role_counts": role_counts,
        "project_total": Project.objects.count(),
        "project_published": Project.objects.filter(status=ProjectStatus.PUBLISHED).count(),
        "job_total": Job.objects.count(),
        "job_open": Job.objects.filter(status=JobStatus.OPEN).count(),
        "application_total": JobApplication.objects.count(),
        "application_pending": JobApplication.objects.filter(
            status=ApplicationStatus.PENDING
        ).count(),
        "contribution_total": ProjectContribution.objects.count(),
        "contribution_confirmed": ProjectContribution.objects.filter(
            status=ContributionStatus.CONFIRMED
        ).count(),
        "disputed": disputed,
        "recent_users": (
            User.objects.select_related("expert_profile").order_by("-date_joined")[:8]
        ),
        "recent_jobs": (
            Job.objects.select_related("published_by")
            .prefetch_related("applications")
            .order_by("-created_at")[:8]
        ),
        "recent_projects": (
            Project.objects.select_related("published_by")
            .prefetch_related("contributions")
            .order_by("-updated_at")[:8]
        ),
    }
    return render(request, "adminpanel/dashboard.html", context)


@_require_system_admin
def admin_user_list(request):
    """All accounts with search, filterable by role."""
    if not is_system_admin(request.user):
        raise PermissionDenied(_("Only system administrators can access this page."))

    qs = User.objects.select_related("expert_profile").order_by("-date_joined")
    role = request.GET.get("role", "")
    if role in Role.values:
        qs = qs.filter(role=role)
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
            | Q(professional_id__icontains=q)
            | Q(organisation_name__icontains=q)
        )

    context = {
        "users": qs[:200],
        "total": qs.count(),
        "role": role,
        "query": q,
    }
    return render(request, "adminpanel/user_list.html", context)


@_require_system_admin
@require_http_methods(["GET", "POST"])
def admin_user_edit(request, pk):
    """Edit a user's role, organisation and account status."""
    if not is_system_admin(request.user):
        raise PermissionDenied(_("Only system administrators can access this page."))
    user = get_object_or_404(User, pk=pk)

    if request.method == "POST":
        form = AdminUserForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, _("User “%(email)s” updated.") % {"email": user.email})
            return redirect("adminpanel:user_list")
    else:
        form = AdminUserForm(instance=user)

    return render(
        request,
        "adminpanel/user_form.html",
        {"form": form, "target": user},
    )


@_require_system_admin
@require_http_methods(["POST"])
def admin_user_toggle_active(request, pk):
    """Deactivate / reactivate an account (soft delete preserves data)."""
    if not is_system_admin(request.user):
        raise PermissionDenied(_("Only system administrators can access this page."))
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, _("You cannot deactivate your own account."))
        return redirect("adminpanel:user_list")
    if user.is_superuser and not request.user.is_superuser:
        messages.error(request, _("You cannot manage another superuser's account."))
        return redirect("adminpanel:user_list")
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    state = _("activated") if user.is_active else _("deactivated")
    messages.success(
        request,
        _("User “%(email)s” was %(state)s.")
        % {"email": user.email, "state": state},
    )
    return redirect("adminpanel:user_list")


@_require_system_admin
@require_http_methods(["POST"])
def admin_user_delete(request, pk):
    """Permanently remove an account (prefer deactivation for users with data)."""
    if not is_system_admin(request.user):
        raise PermissionDenied(_("Only system administrators can access this page."))
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, _("You cannot delete your own account."))
        return redirect("adminpanel:user_list")
    email = user.email
    user.delete()
    messages.success(request, _("User “%(email)s” deleted.") % {"email": email})
    return redirect("adminpanel:user_list")


@_require_system_admin
def admin_job_list(request):
    """All job offers, across companies."""
    if not is_system_admin(request.user):
        raise PermissionDenied(_("Only system administrators can access this page."))
    jobs = (
        Job.objects.select_related("published_by")
        .prefetch_related("applications")
        .order_by("-created_at")
    )
    return render(request, "adminpanel/job_list.html", {"jobs": jobs})


@_require_system_admin
def admin_project_list(request):
    """All projects, across companies."""
    if not is_system_admin(request.user):
        raise PermissionDenied(_("Only system administrators can access this page."))
    projects = (
        Project.objects.select_related("published_by")
        .prefetch_related("contributions")
        .order_by("-updated_at")
    )
    return render(
        request,
        "adminpanel/project_list.html",
        {"projects": projects},
    )


@_require_system_admin
def admin_application_list(request):
    """All applications and their decisions."""
    if not is_system_admin(request.user):
        raise PermissionDenied(_("Only system administrators can access this page."))
    applications = (
        JobApplication.objects.select_related("job", "job__published_by", "applicant")
        .order_by("-applied_at")
    )
    status = request.GET.get("status", "")
    if status in ApplicationStatus.values:
        applications = applications.filter(status=status)
    return render(
        request,
        "adminpanel/application_list.html",
        {
            "applications": applications,
            "status": status,
            "status_pending": ApplicationStatus.PENDING,
            "status_accepted": ApplicationStatus.ACCEPTED,
            "status_rejected": ApplicationStatus.REJECTED,
        },
    )
