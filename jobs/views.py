"""
Job board views: public list/detail, company publish + application review,
expert apply. Decisions and applications go through jobs.services.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView, ListView

from certification.models import ContributionStatus

from .forms import ApplicationForm, JobForm
from .models import ApplicationStatus, Job, JobApplication, JobStatus
from .services import JobsError, apply_to_job, close_job, decide_application


class JobListView(ListView):
    """Public job board: open offers first."""

    model = Job
    context_object_name = "jobs"
    template_name = "jobs/list.html"
    paginate_by = 12
    queryset = (
        Job.objects.filter(status=JobStatus.OPEN)
        .select_related("published_by")
        .prefetch_related("applications")
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["closed_count"] = Job.objects.filter(status=JobStatus.CLOSED).count()
        return context


class JobPublicDetailView(DetailView):
    model = Job
    template_name = "jobs/detail.html"
    context_object_name = "job"

    def get_queryset(self):
        return Job.objects.select_related("published_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        job = self.object
        user = self.request.user
        context["my_application"] = job.application_for(user)
        if user.is_authenticated:
            context["certified_count"] = user.contributions.filter(
                status=ContributionStatus.CONFIRMED
            ).count()
        return context


@login_required
def job_create(request):
    """Any user publishes a job offer."""
    if request.method == "POST":
        form = JobForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.published_by = request.user
            job.save()
            messages.success(
            request,
            _("Offre de mission publiée : les experts peuvent maintenant candidater."),
        )
            return redirect("jobs:detail", pk=job.pk)
    else:
        form = JobForm()
    return render(request, "jobs/form.html", {"form": form})


@login_required
def job_update(request, pk):
    """Owner edits a published job offer."""
    job = get_object_or_404(Job, pk=pk)
    if job.published_by_id != request.user.pk and not request.user.is_superuser:
        raise PermissionDenied(_("Seule la structure qui a publié cette mission peut la modifier."))

    if request.method == "POST":
        form = JobForm(request.POST, instance=job)
        if form.is_valid():
            form.save()
            messages.success(request, _("Offre de mission mise à jour."))
            return redirect("jobs:manage", pk=job.pk)
    else:
        form = JobForm(instance=job)
    return render(request, "jobs/form.html", {"form": form, "job": job, "editing": True})


@require_http_methods(["POST"])
@login_required
def job_delete(request, pk):
    """Owner deletes a job offer (and, cascading, its applications)."""
    job = get_object_or_404(Job, pk=pk)
    if job.published_by_id != request.user.pk and not request.user.is_superuser:
        raise PermissionDenied(
            _("Seule la structure qui a publié cette mission peut la supprimer.")
        )
    if job.status == JobStatus.OPEN:
        messages.error(
            request,
            _(
                "Clôturez l'offre avant de la supprimer, afin de donner une réponse finale"
                " aux candidats."
            ),
        )
        return redirect("jobs:manage", pk=job.pk)
    job.delete()
    messages.success(request, _("Offre de mission supprimée."))
    return redirect("jobs:list")


@login_required
def my_jobs(request):
    """A user's own job offers (management hub)."""
    jobs = (
        request.user.published_jobs.select_related("published_by")
        .prefetch_related("applications")
        .order_by("-created_at")
    )
    return render(
        request,
        "jobs/my_jobs.html",
        {
            "jobs": jobs,
            "status_open": JobStatus.OPEN,
            "status_closed": JobStatus.CLOSED,
            "status_pending": ApplicationStatus.PENDING,
        },
    )


@login_required
def my_applications(request):
    """A user's own applications."""
    applications = JobApplication.objects.filter(applicant=request.user).select_related(
        "job", "job__published_by"
    )
    return render(
        request,
        "jobs/my_applications.html",
        {
            "applications": applications,
            "status_pending": ApplicationStatus.PENDING,
            "status_accepted": ApplicationStatus.ACCEPTED,
            "status_rejected": ApplicationStatus.REJECTED,
        },
    )


@login_required
def job_apply(request, pk):
    """A user applies to one job."""
    job = get_object_or_404(Job, pk=pk)
    existing = job.application_for(request.user)

    if request.method == "POST" and not existing:
        form = ApplicationForm(request.POST)
        try:
            if form.is_valid():
                apply_to_job(job, request.user, form.cleaned_data["cover_letter"])
                messages.success(
                    request,
                    _("Candidature envoyée : la structure a été notifiée."),
                )
                return redirect("jobs:my_applications")
        except (JobsError, ValidationError) as error:
            messages.error(request, str(error))
            return redirect("jobs:detail", pk=job.pk)
    else:
        form = ApplicationForm()
    return render(
        request,
        "jobs/apply.html",
        {"job": job, "form": form, "my_application": existing},
    )


@login_required
def application_update(request, pk):
    """Expert edits the cover letter of their own pending application."""
    application = get_object_or_404(JobApplication.objects.select_related("job"), pk=pk)
    if application.applicant_id != request.user.pk:
        raise PermissionDenied(_("Vous ne pouvez modifier que vos propres candidatures."))
    if application.status != ApplicationStatus.PENDING:
        messages.error(
            request,
            _("Cette candidature a déjà été décidée et ne peut plus être modifiée."),
        )
        return redirect("jobs:my_applications")

    if request.method == "POST":
        form = ApplicationForm(request.POST)
        if form.is_valid():
            application.cover_letter = form.cleaned_data["cover_letter"]
            application.save(update_fields=["cover_letter"])
            messages.success(request, _("Candidature mise à jour."))
            return redirect("jobs:my_applications")
    else:
        form = ApplicationForm(initial={"cover_letter": application.cover_letter})
    return render(
        request,
        "jobs/apply.html",
        {"job": application.job, "form": form, "application": application, "editing": True},
    )


@require_http_methods(["POST"])
@login_required
def application_withdraw(request, pk):
    """Expert withdraws (deletes) their own application."""
    application = get_object_or_404(JobApplication, pk=pk)
    if application.applicant_id != request.user.pk:
        raise PermissionDenied(_("Vous ne pouvez retirer que vos propres candidatures."))
    title = application.job.title
    application.delete()
    messages.success(
        request,
        _("Votre candidature à « %(title)s » a été retirée.") % {"title": title},
    )
    return redirect("jobs:my_applications")


@login_required
def job_manage(request, pk):
    """
    Company workspace for one offer: review applications (accept / decline),
    close the job.
    """
    job = get_object_or_404(Job.objects.select_related("published_by"), pk=pk)
    if job.published_by_id != request.user.pk and not request.user.is_superuser:
        raise PermissionDenied(_("Seule la structure qui a publié cette mission peut la gérer."))

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action in ("accept", "decline"):
                application = get_object_or_404(
                    JobApplication,
                    pk=request.POST.get("application_pk"),
                    job=job,
                )
                decide_application(application, request.user, accept=(action == "accept"))
                messages.success(
                    request,
                    _("Décision enregistrée : le candidat a été notifié."),
                )
            elif action == "close":
                close_job(job, request.user)
                messages.success(
                    request,
                    _("Mission clôturée : elle n'accepte plus de candidatures."),
                )
        except JobsError as error:
            messages.error(request, str(error))
        return redirect("jobs:manage", pk=job.pk)

    applications = job.applications.select_related(
        "applicant", "applicant__expert_profile"
    ).prefetch_related("applicant__contributions")
    pending_count = applications.filter(status=ApplicationStatus.PENDING).count()
    return render(
        request,
        "jobs/manage.html",
        {
            "job": job,
            "applications": applications,
            "pending_count": pending_count,
            "status_pending": ApplicationStatus.PENDING,
            "status_accepted": ApplicationStatus.ACCEPTED,
            "status_rejected": ApplicationStatus.REJECTED,
            "status_open": JobStatus.OPEN,
        },
    )
