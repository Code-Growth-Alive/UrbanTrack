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
    """
    An authenticated account with admin privileges: the ``admin`` role or a
    Django superuser. Non-superuser admins are granted by a superuser.
    """
    return bool(getattr(user, "is_authenticated", False)) and (
        user.is_superuser or getattr(user, "is_admin_role", False)
    )


@_require_system_admin
def admin_dashboard(request):
    """Operational overview: key counts + recent items per domain."""
    if not is_system_admin(request.user):
        raise PermissionDenied(
            _("Seuls les administrateurs du système peuvent accéder à cette page.")
        )

    by_role = User.objects.values("role").annotate(count=Count("id")).order_by("role")
    role_counts = {row["role"]: row["count"] for row in by_role}
    role_counts["total"] = sum(role_counts.values())
    role_counts["confirmed"] = User.objects.filter(email_confirmed=True).count()

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
        raise PermissionDenied(
            _("Seuls les administrateurs du système peuvent accéder à cette page.")
        )

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
            | Q(company__name__icontains=q)
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
        raise PermissionDenied(
            _("Seuls les administrateurs du système peuvent accéder à cette page.")
        )
    user = get_object_or_404(User, pk=pk)

    if request.method == "POST":
        form = AdminUserForm(request.POST, instance=user, acting_user=request.user)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                _("Utilisateur « %(email)s » mis à jour.") % {"email": user.email},
            )
            return redirect("adminpanel:user_list")
    else:
        form = AdminUserForm(instance=user, acting_user=request.user)

    return render(
        request,
        "adminpanel/user_form.html",
        {"form": form, "target": user},
    )


@_require_system_admin
@require_http_methods(["POST"])
def admin_nominate_admin(request, pk):
    """
    Promote or demote a user's ``admin`` role. Only the single platform
    superuser can nominate someone to be an admin.
    """
    if not request.user.is_superuser:
        raise PermissionDenied(_("Only the platform superuser can nominate an admin."))
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(
            request,
            _("Vous ne pouvez pas modifier votre propre rôle d'administrateur."),
        )
        return redirect("adminpanel:user_list")
    if user.is_superuser:
        messages.error(request, _("Les comptes superutilisateur ne peuvent pas être nommés ici."))
        return redirect("adminpanel:user_list")

    make_admin = request.POST.get("make_admin") == "1"
    user.role = Role.ADMIN if make_admin else Role.USER
    user.save(update_fields=["role"])
    action = (
        _("nommé en tant qu'administrateur") if make_admin else _("retiré du rôle d'administrateur")
    )
    messages.success(
        request,
        _("L'utilisateur « %(email)s » a été %(action)s.")
        % {"email": user.email, "action": action},
    )
    return redirect("adminpanel:user_list")


@_require_system_admin
@require_http_methods(["POST"])
def admin_user_toggle_active(request, pk):
    """Deactivate / reactivate an account (soft delete preserves data)."""
    if not is_system_admin(request.user):
        raise PermissionDenied(
            _("Seuls les administrateurs du système peuvent accéder à cette page.")
        )
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, _("Vous ne pouvez pas désactiver votre propre compte."))
        return redirect("adminpanel:user_list")
    if user.is_superuser and not request.user.is_superuser:
        messages.error(
            request,
            _("Vous ne pouvez pas gérer le compte d'un autre superutilisateur."),
        )
        return redirect("adminpanel:user_list")
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    state = _("activé") if user.is_active else _("désactivé")
    messages.success(
        request,
        _("L'utilisateur « %(email)s » a été %(state)s.") % {"email": user.email, "state": state},
    )
    return redirect("adminpanel:user_list")


@_require_system_admin
@require_http_methods(["POST"])
def admin_user_delete(request, pk):
    """Permanently remove an account (prefer deactivation for users with data)."""
    if not is_system_admin(request.user):
        raise PermissionDenied(
            _("Seuls les administrateurs du système peuvent accéder à cette page.")
        )
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, _("Vous ne pouvez pas supprimer votre propre compte."))
        return redirect("adminpanel:user_list")
    email = user.email
    user.delete()
    messages.success(request, _("Utilisateur « %(email)s » supprimé.") % {"email": email})
    return redirect("adminpanel:user_list")


@_require_system_admin
def admin_job_list(request):
    """All job offers, across companies."""
    if not is_system_admin(request.user):
        raise PermissionDenied(
            _("Seuls les administrateurs du système peuvent accéder à cette page.")
        )
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
        raise PermissionDenied(
            _("Seuls les administrateurs du système peuvent accéder à cette page.")
        )
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
        raise PermissionDenied(
            _("Seuls les administrateurs du système peuvent accéder à cette page.")
        )
    applications = JobApplication.objects.select_related(
        "job", "job__published_by", "applicant"
    ).order_by("-applied_at")
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
