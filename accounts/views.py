"""
Account views: public expert profile, expert directory, expert search,
signup with email confirmation and the unified user dashboard.
"""

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.contrib.auth.views import PasswordChangeView as DjangoPasswordChangeView
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DetailView, FormView, ListView

from projects.models import Project, ProjectStatus, ProjectVisibility

from .email_confirmation import (
    ConfirmationError,
    confirm_email,
    issue_confirmation_code,
)
from .forms import (
    AccountSettingsForm,
    ConfirmEmailForm,
    EmailChangeForm,
    EmailOrUsernameAuthenticationForm,
    SignUpForm,
)
from .models import User


class PublicExpertProfileView(DetailView):
    model = User
    slug_field = "professional_id"
    slug_url_kwarg = "professional_id"
    template_name = "experts/profile.html"
    context_object_name = "expert"

    def get_queryset(self):
        # Every user owns a public portfolio profile.
        return User.objects.filter(email_confirmed=True)

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
            # T7: certified synthesis indicators computed from confirmed
            # contributions only — never hand-entered.
            indicators=profile.synthesis_indicators() if contributions else {},
            seo_title=f"{self.object.get_full_name() or self.object.username} : Urban Track",
            seo_description=(
                profile.headline
                or f"Profil public de {self.object.get_full_name() or self.object.username}"
                f" sur Urban Track."
            ),
            seo_image=self.request.build_absolute_uri(
                self.object.avatar.url
                if getattr(getattr(self.object, "avatar", None), "name", "")
                else static("img/hero-city.jpg")
            ),
            seo_url=self.request.build_absolute_uri(
                reverse("accounts:public_profile", args=[self.object.professional_id])
            ),
        )
        return context


class PublicCompanyView(DetailView):
    model = None
    template_name = "accounts/company.html"
    context_object_name = "company"

    def get_object(self, queryset=None):
        from .models import Company

        return get_object_or_404(Company, pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = self.object
        approved_members = company.approved_members().select_related("expert_profile")
        projects = (
            Project.objects.filter(
                published_by__company=company,
                status=ProjectStatus.PUBLISHED,
                visibility=ProjectVisibility.PUBLIC,
            )
            .select_related("published_by", "country", "client", "funder")
            .order_by("-updated_at")
        )
        context.update(
            approved_members=approved_members,
            projects=projects,
            company_stats={
                "members": approved_members.count(),
                "projects": projects.count(),
            },
            seo_title=f"{company.name} : Urban Track",
            seo_description=(
                company.description
                or f"Fiche société publique de {company.name} sur Urban Track."
            ),
            seo_image=self.request.build_absolute_uri(static("img/hero-building.jpg")),
            seo_url=self.request.build_absolute_uri(company.get_absolute_url()),
        )
        return context


class ExpertListView(ListView):
    """Public directory of every (confirmed) user's portfolio."""

    model = User
    context_object_name = "experts"
    template_name = "experts/list.html"
    paginate_by = 24

    def get_queryset(self):
        qs = (
            User.objects.filter(email_confirmed=True)
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
    JSON autocomplete source for the contributor declaration form.

    Matches on name, email and professional ID. Restricted to authenticated
    users: it exposes personal data.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=403)
    term = (request.GET.get("q") or "").strip()
    queryset = User.objects.filter(email_confirmed=True)
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

    def get_success_url(self):
        user = self.request.user
        if user.is_authenticated and not user.email_confirmed:
            return reverse_lazy("accounts:confirm_email")
        return reverse_lazy("accounts:dashboard")

    def get_default_redirect_url(self):
        """Route unconfirmed logins straight to the confirmation page."""
        user = getattr(self.request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and not getattr(user, "email_confirmed", True)
        ):
            return reverse_lazy("accounts:confirm_email")
        return super().get_default_redirect_url()


class LogOutView(DjangoLogoutView):
    next_page = reverse_lazy("home")

    def get_next_page(self):
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        if next_url:
            from django.utils.http import url_has_allowed_host_and_scheme

            if url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={self.request.get_host()},
                require_https=self.request.is_secure(),
            ):
                return next_url
        return super().get_next_page()


@login_required
def dashboard(request):
    """
    Unified workspace for every user: their projects (all users can publish),
    pending contributor reviews and certified track record.
    """
    from certification.models import ContributionStatus, ProjectContribution

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
    profile = getattr(request.user, "expert_profile", None)
    pending_reviews = (
        request.user.contributions.filter(
            status__in=ContributionStatus.actionable(),
            pending_company_validation=False,
        )
        .select_related("project", "added_by")
        .order_by("-created_at")
    )
    confirmed = profile.confirmed_contributions() if profile else []

    # T2: membership approval queue for company administrators + the user's
    # own pending affiliation request.
    pending_membership = request.user.pending_membership
    membership_queue = []
    if request.user.company_id and request.user.is_company_admin:
        membership_queue = list(
            request.user.company.pending_memberships().exclude(user=request.user)
        )

    context = {
        "projects": projects,
        "awaiting_validation": awaiting_validation,
        "pending_membership": pending_membership,
        "membership_queue": membership_queue,
        "counts": {
            "drafts": projects.filter(status="draft").count(),
            "published": projects.filter(status="published").count(),
            "archived": projects.filter(status="archived").count(),
        },
        "open_jobs": request.user.published_jobs.filter(status="open"),
        "pending_reviews": pending_reviews,
        "confirmed_contributions": confirmed,
        "trust_score": profile.trust_score() if profile else 0,
        "show_launch_stats": any(
            value >= settings.LAUNCH_COUNTER_THRESHOLD
            for value in (
                projects.count(),
                pending_reviews.count(),
                profile.trust_score() if profile else 0,
            )
        ),
        "my_applications": (request.user.job_applications.select_related("job")[:5]),
    }
    return render(request, "accounts/dashboard.html", context)


def trust_score_methodology(request):
    """Public explanation of the trust-score formula used across the site."""
    return render(
        request,
        "accounts/trust_score.html",
        {
            "role_weights": [
                ("director", 4),
                ("manager", 3),
                ("specialist", 2),
                ("consultant", 2),
                ("engineer", 2),
                ("assistant", 1),
                ("other", 1),
            ],
        },
    )


class SignUpView(FormView):
    """Account creation; issues a 6-digit email confirmation code."""

    template_name = "accounts/signup.html"
    form_class = SignUpForm
    success_url = reverse_lazy("accounts:confirm_email")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("accounts:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.create_user()
        issue_confirmation_code(user)
        self.request.session["pending_confirm_email"] = user.email
        login(self.request, user)
        return redirect(self.get_success_url())


class ConfirmEmailView(FormView):
    """Enter the 6-digit code emailed after signup (or email change)."""

    template_name = "accounts/confirm_email.html"
    form_class = ConfirmEmailForm
    success_url = reverse_lazy("accounts:dashboard")

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect("accounts:login")
        if user.email_confirmed:
            return redirect("accounts:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        # A first-time signup is a user who never confirmed any email: the
        # session marker set by SignUpView gives an honest signal.
        context = super().get_context_data(**kwargs)
        context["first_time_signup"] = (
            self.request.session.get("pending_confirm_email") == self.request.user.email
        )
        return context

    def form_valid(self, form):
        user = self.request.user
        try:
            confirm_email(user, form.cleaned_data["code"])
        except ConfirmationError as error:
            form.add_error("code", str(error))
            return self.form_invalid(form)
        return redirect(self.get_success_url())


def resend_confirmation_code(request):
    """Resend the 6-digit code for the current (unconfirmed) user."""
    if request.method == "POST" and request.user.is_authenticated:
        if not request.user.email_confirmed:
            issue_confirmation_code(request.user)
        return redirect("accounts:confirm_email")
    return redirect("accounts:confirm_email")


@require_POST
@login_required
def correct_signup_email(request):
    """
    Let a first-time signup fix a mistyped email before the account is
    purged. Restricted to unconfirmed accounts that just signed up (the
    session marker set by SignUpView), so a confirmed account's email can
    never be redirected by this route.
    """
    from django.contrib import messages

    user = request.user
    original_email = request.session.get("pending_confirm_email")
    if user.email_confirmed or original_email != user.email:
        return redirect("accounts:dashboard")
    form = EmailChangeForm(request.POST, instance=user)
    if form.is_valid():
        new_email = form.cleaned_data["email"]
        user = form.save(commit=False)
        if user.username == original_email:
            user.username = new_email
        user.email_confirmed = False
        user.save()
        issue_confirmation_code(user)
        request.session["pending_confirm_email"] = new_email
        messages.success(
            request,
            _(
                "Adresse email corrigée : un nouveau code de confirmation "
                "a été envoyé à %(email)s."
            )
            % {"email": new_email},
        )
    else:
        for error in form.errors.get("email", []):
            messages.error(request, error)
    return redirect("accounts:confirm_email")


# ---------------------------------------------------------------------------
# Portfolio self-service (each user edits their own contextual profile data)
# ---------------------------------------------------------------------------


@login_required
def profile_edit(request):
    """Edit the full contextual portfolio (bio, skills, trainings, positions,
    mandates, publications, teaching, media, languages…) plus CV preference."""
    from django.contrib import messages

    from .portfolio_forms import (
        MandateFormSet,
        MediaFormSet,
        PositionFormSet,
        ProfileForm,
        PublicationFormSet,
        SkillsForm,
        TeachingFormSet,
        TrainingFormSet,
    )

    profile = request.user.expert_profile
    formset_kwargs = {"instance": profile}

    def _initial_profile_data(profile):
        def join(items):
            return ", ".join(items)

        languages = "\n".join(
            "{name}, {read}, {spoken}, {written}".format(
                **{k: (v or "") for k, v in entry.items()}
            )
            for entry in profile.languages
            if entry.get("name")
        )
        return {
            "strengths": join(profile.strengths or []),
            "countries_of_intervention": join(profile.countries_of_intervention or []),
            "languages": languages,
        }

    if request.method == "POST":
        profile_form = ProfileForm(request.POST, instance=profile)
        skills_form = SkillsForm(request.POST)
        training_formset = TrainingFormSet(request.POST, **formset_kwargs)
        position_formset = PositionFormSet(request.POST, **formset_kwargs)
        mandate_formset = MandateFormSet(request.POST, **formset_kwargs)
        publication_formset = PublicationFormSet(request.POST, **formset_kwargs)
        teaching_formset = TeachingFormSet(request.POST, **formset_kwargs)
        media_formset = MediaFormSet(request.POST, **formset_kwargs)
        formsets = [
            training_formset,
            position_formset,
            mandate_formset,
            publication_formset,
            teaching_formset,
            media_formset,
        ]
        if profile_form.is_valid() and skills_form.is_valid() and all(
            fs.is_valid() for fs in formsets
        ):
            profile_form.save()
            skills_form.save(profile)
            for fs in formsets:
                fs.save()
            messages.success(request, _("Portfolio mis à jour."))
            return redirect("accounts:profile_edit")
    else:
        initial_skills = ", ".join(skill.name for skill in profile.skills.all().order_by("name"))
        profile_form = ProfileForm(
            instance=profile, initial=_initial_profile_data(profile)
        )
        skills_form = SkillsForm(initial={"skills": initial_skills})
        training_formset = TrainingFormSet(**formset_kwargs)
        position_formset = PositionFormSet(**formset_kwargs)
        mandate_formset = MandateFormSet(**formset_kwargs)
        publication_formset = PublicationFormSet(**formset_kwargs)
        teaching_formset = TeachingFormSet(**formset_kwargs)
        media_formset = MediaFormSet(**formset_kwargs)

    return render(
        request,
        "accounts/profile_edit.html",
        {
            "profile": profile,
            "profile_form": profile_form,
            "skills_form": skills_form,
            "training_formset": training_formset,
            "position_formset": position_formset,
            "mandate_formset": mandate_formset,
            "publication_formset": publication_formset,
            "teaching_formset": teaching_formset,
            "media_formset": media_formset,
        },
    )


@login_required
def set_cv_template(request):
    """Save the preferred CV skin from the CV builder screen."""
    from django.contrib import messages

    from .models import CvTemplate

    if request.method == "POST":
        template = request.POST.get("cv_template")
        if template in CvTemplate.values:
            request.user.expert_profile.cv_template = template
            request.user.expert_profile.save(update_fields=["cv_template", "updated_at"])
            messages.success(request, _("Modèle de CV préféré enregistré."))
    return redirect("cv_generator:builder")


# ---------------------------------------------------------------------------
# Account settings: personal details + profile picture + email + password
# ---------------------------------------------------------------------------


@login_required
def account_settings(request):
    from django.contrib import messages

    if request.method == "POST":
        # Capture before the model form mutates the instance in memory.
        previous_company_id = request.user.company_id
        form = AccountSettingsForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            new_company = form.cleaned_data.get("company")
            if new_company is not None and new_company.pk != previous_company_id:
                # T2: switching company opens a membership request, never an
                # implicit join. The affiliation is kept pending until an
                # administrator of the target company approves it.
                from .models import MembershipStatus

                membership = new_company.request_membership(request.user)
                if membership.status == MembershipStatus.APPROVED:
                    request.user.company = new_company
                    request.user.save(update_fields=["company"])
                else:
                    request.user.company = None
                    request.user.save(update_fields=["company"])
                    messages.success(
                        request,
                        _(
                            "Une demande d'affiliation a été envoyée aux administrateurs "
                            "de %(company)s. Une fois approuvée, elle apparaîtra sur votre profil."
                        )
                        % {"company": new_company.name},
                    )
                    return redirect("accounts:settings")
            messages.success(request, _("Paramètres du compte mis à jour."))
            return redirect("accounts:settings")
    else:
        form = AccountSettingsForm(instance=request.user)

    return render(
        request,
        "accounts/settings.html",
        {"form": form},
    )


@login_required
@require_POST
def company_membership_action(request, pk):
    """
    Approve or decline a pending company membership (T2).

    Only an approved administrator of the company may act. The review is
    recorded on the membership (``reviewed_by``/``reviewed_at``) for audit.
    """
    from django.contrib import messages

    from .models import CompanyMembership

    membership = get_object_or_404(
        CompanyMembership.objects.select_related("company", "user"), pk=pk
    )
    if not membership.company.is_admin(request.user):
        raise PermissionDenied(
            _("Seul un administrateur de cette structure peut examiner les affiliations.")
        )

    action = request.POST.get("action")
    if action == "approve":
        membership.company.approve_membership(membership, reviewed_by=request.user)
        messages.success(
            request,
            _("%(name)s est désormais membre de %(company)s.")
            % {"name": membership.user.get_full_name() or membership.user.username,
               "company": membership.company.name},
        )
    elif action == "decline":
        membership.company.decline_membership(membership, reviewed_by=request.user)
        messages.success(
            request,
            _("La demande d'affiliation de %(name)s a été refusée.")
            % {"name": membership.user.get_full_name() or membership.user.username},
        )
    else:
        messages.error(request, _("Action d'affiliation inconnue."))
    return redirect("accounts:dashboard")


@login_required
def change_email(request):
    """
    Change the account email. The new email is stored immediately but the
    account is marked unconfirmed again and a fresh code is required before
    the change is complete.
    """
    from django.contrib import messages

    if request.method == "POST":
        form = EmailChangeForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            user.email_confirmed = False
            user.save()
            issue_confirmation_code(user)
            messages.success(
                request,
                _(
                    "Un code de confirmation a été envoyé à votre nouvelle adresse email. "
                    "Saisissez-le pour finaliser le changement."
                ),
            )
            return redirect("accounts:confirm_email")
    else:
        form = EmailChangeForm(instance=request.user)

    return render(
        request,
        "accounts/email_change.html",
        {"form": form},
    )


class PasswordChangeView(DjangoPasswordChangeView):
    """Change password inside the account settings wizard."""

    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:settings")

    def form_valid(self, form):
        from django.contrib import messages

        messages.success(self.request, _("Votre mot de passe a été modifié."))
        return super().form_valid(form)
