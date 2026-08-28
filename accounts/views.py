"""
Account views: ResearchGate-style public expert profile, expert directory,
expert search (autocomplete source), role-aware signup and the per-role
dashboard.
"""

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.contrib.auth.views import PasswordChangeView as DjangoPasswordChangeView
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET
from django.views.generic import DetailView, FormView, ListView

from .forms import AccountSettingsForm, EmailOrUsernameAuthenticationForm, SignUpForm
from .models import Role, User


class PublicExpertProfileView(DetailView):
    model = User
    slug_field = "professional_id"
    slug_url_kwarg = "professional_id"
    queryset = User.objects.filter(role=Role.EXPERT)
    template_name = "experts/profile.html"
    context_object_name = "expert"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = getattr(self.object, "expert_profile", None)
        contributions = list(profile.confirmed_contributions()) if profile else []
        by_role = {}
        for contribution in contributions:
            by_role[contribution.role_type] = by_role.get(contribution.role_type, 0) + 1
        context.update(
            profile=profile,
            confirmed_contributions=contributions,
            stats={
                "total": len(contributions),
                "director": by_role.get("director", 0),
                "manager": by_role.get("manager", 0),
                "specialist": by_role.get("specialist", 0),
                "assistant": by_role.get("assistant", 0),
            },
            trust_score=profile.trust_score() if profile else 0,
        )
        return context


class ExpertListView(ListView):
    """Public directory of individual experts (browse entry point)."""

    model = User
    context_object_name = "experts"
    template_name = "experts/list.html"
    paginate_by = 24

    def get_queryset(self):
        qs = (
            User.objects.filter(role=Role.EXPERT)
            .select_related("expert_profile")
            .order_by("-date_joined")
        )
        q = (self.request.GET.get("q") or "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(email__icontains=q)
                | Q(professional_id__icontains=q)
                | Q(expert_profile__headline__icontains=q)
                | Q(expert_profile__city__icontains=q)
                | Q(expert_profile__country__icontains=q)
                | Q(expert_profile__skills__name__icontains=q)
            ).distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["query"] = (self.request.GET.get("q") or "").strip()
        return ctx


@require_GET
def expert_search(request):
    """
    JSON autocomplete source for the contributor declaration form (Epic 2).

    Matches on name, email and professional ID. Restricted to authenticated
    company users: it exposes personal data.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=403)
    term = (request.GET.get("q") or "").strip()
    queryset = User.objects.filter(role=Role.EXPERT)
    if term:
        from django.db.models import Q

        queryset = queryset.filter(
            Q(first_name__icontains=term)
            | Q(last_name__icontains=term)
            | Q(email__icontains=term)
            | Q(professional_id__icontains=term)
        )
    results = [
        {
            "email": user.email,
            "name": user.get_full_name() or user.username,
            "professional_id": user.professional_id,
        }
        for user in queryset.order_by("first_name", "last_name")[:8]
    ]
    return JsonResponse({"results": results})


class LogInView(DjangoLoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True
    form_class = EmailOrUsernameAuthenticationForm


class LogOutView(DjangoLogoutView):
    next_page = reverse_lazy("home")


@login_required
def dashboard(request):
    """
    Role-aware workspace (Epic 2/3 companion screens).

    Companies: their projects with lifecycle status plus the contributions
    whose adjusted wording awaits THEIR validation. Experts: the
    declarations awaiting their review, with one-click access to the review
    page, and a summary of what is already certified.
    """
    from certification.models import ContributionStatus, ProjectContribution

    context = {"role": request.user.role}

    if request.user.is_company or request.user.is_donor or request.user.is_superuser:
        projects = (
            request.user.published_projects.select_related("published_by")
            .prefetch_related("contributions")
            .order_by("-updated_at")
        )
        awaiting_validation = (
            ProjectContribution.objects.filter(
                project__published_by=request.user,
                status=ContributionStatus.PENDING_CONFIRMATION,
                pending_company_validation=True,
            )
            .select_related("project", "expert")
            .order_by("updated_at")
        )
        context.update(
            projects=projects,
            awaiting_validation=awaiting_validation,
            counts={
                "drafts": projects.filter(status="draft").count(),
                "published": projects.filter(status="published").count(),
                "archived": projects.filter(status="archived").count(),
            },
            open_jobs=request.user.published_jobs.filter(status="open"),
        )
    elif request.user.is_expert:
        profile = getattr(request.user, "expert_profile", None)
        pending = (
            request.user.contributions.filter(
                status__in=ContributionStatus.actionable(),
                pending_company_validation=False,
            )
            .select_related("project", "added_by")
            .order_by("-created_at")
        )
        confirmed = profile.confirmed_contributions() if profile else []
        context.update(
            pending_reviews=pending,
            confirmed_contributions=confirmed,
            trust_score=profile.trust_score() if profile else 0,
            my_applications=(request.user.job_applications.select_related("job")[:5]),
        )

    return render(request, "accounts/dashboard.html", context)


class SignUpView(FormView):
    """Role-aware account creation (Epic -1 / landing fallback)."""

    template_name = "accounts/signup.html"
    form_class = SignUpForm
    success_url = reverse_lazy("accounts:dashboard")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("accounts:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.create_user()
        login(self.request, user)
        return redirect(self.get_success_url())


# ---------------------------------------------------------------------------
# Portfolio self-service (experts edit their own contextual profile data)
# ---------------------------------------------------------------------------


@login_required
def profile_edit(request):
    """Edit headline, bio, location, skills, trainings and CV preference."""
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied
    from django.utils.translation import gettext as _

    from .portfolio_forms import ProfileForm, SkillsForm, TrainingFormSet

    if not request.user.is_expert:
        raise PermissionDenied(_("Only expert accounts have a portfolio."))
    profile = request.user.expert_profile

    if request.method == "POST":
        profile_form = ProfileForm(request.POST, instance=profile)
        skills_form = SkillsForm(request.POST)
        formset = TrainingFormSet(request.POST, instance=profile)
        if profile_form.is_valid() and skills_form.is_valid() and formset.is_valid():
            profile_form.save()
            skills_form.save(profile)
            formset.save()
            messages.success(request, _("Portfolio updated."))
            return redirect("accounts:profile_edit")
    else:
        initial_skills = ", ".join(skill.name for skill in profile.skills.all().order_by("name"))
        profile_form = ProfileForm(instance=profile)
        skills_form = SkillsForm(initial={"skills": initial_skills})
        formset = TrainingFormSet(instance=profile)

    return render(
        request,
        "accounts/profile_edit.html",
        {
            "profile": profile,
            "profile_form": profile_form,
            "skills_form": skills_form,
            "formset": formset,
        },
    )


@login_required
def set_cv_template(request):
    """Save the preferred CV skin from the CV builder screen."""
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied
    from django.utils.translation import gettext as _

    from .models import CvTemplate

    if not request.user.is_expert:
        raise PermissionDenied(_("Only expert accounts can choose a CV template."))
    if request.method == "POST":
        template = request.POST.get("cv_template")
        if template in CvTemplate.values:
            request.user.expert_profile.cv_template = template
            request.user.expert_profile.save(update_fields=["cv_template", "updated_at"])
            messages.success(request, _("Preferred CV template saved."))
    return redirect("cv_generator:builder")


# ---------------------------------------------------------------------------
# Account settings: personal details + profile picture + password
# ---------------------------------------------------------------------------


@login_required
def account_settings(request):
    """Edit personal details and the profile picture shared by all roles."""
    from django.contrib import messages
    from django.utils.translation import gettext as _

    if request.method == "POST":
        form = AccountSettingsForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Account settings updated."))
            return redirect("accounts:settings")
    else:
        form = AccountSettingsForm(instance=request.user)

    return render(
        request,
        "accounts/settings.html",
        {"form": form},
    )


class PasswordChangeView(DjangoPasswordChangeView):
    """Change password inside the account settings wizard."""

    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:settings")

    def form_valid(self, form):
        from django.contrib import messages
        from django.utils.translation import gettext as _

        messages.success(self.request, _("Your password has been changed."))
        return super().form_valid(form)
