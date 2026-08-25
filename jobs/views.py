"""
Job board views: public list/detail, company publish + application review,
expert apply. Decisions and applications go through jobs.services.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
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
        if user.is_authenticated and user.is_expert:
            context["certified_count"] = user.contributions.filter(
                status=ContributionStatus.CONFIRMED
            ).count()
        return context


@login_required
def job_create(request):
    """Company/donor publishes a job offer."""
    if not (request.user.is_company or request.user.is_donor or request.user.is_superuser):
        raise PermissionDenied(_("Only company accounts can publish job offers."))

    if request.method == "POST":
        form = JobForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.published_by = request.user
            job.save()
            messages.success(request, _("Job offer published: experts can now apply."))
            return redirect("jobs:detail", pk=job.pk)
    else:
        form = JobForm()
    return render(request, "jobs/form.html", {"form": form})


@login_required
def my_applications(request):
    """Expert view of their own applications."""
    if not request.user.is_expert:
        raise PermissionDenied(_("Only expert accounts have applications."))
    applications = JobApplication.objects.filter(applicant=request.user).select_related(
        "job", "job__published_by"
    )
    return render(
        request,
        "jobs/my_applications.html",
        {
            "applications": applications,
            "status_accepted": ApplicationStatus.ACCEPTED,
            "status_rejected": ApplicationStatus.REJECTED,
        },
    )


@login_required
def job_apply(request, pk):
    """Expert applies to one job."""
    job = get_object_or_404(Job, pk=pk)
    if not request.user.is_expert:
        raise PermissionDenied(_("Only expert accounts can apply to jobs."))
    existing = job.application_for(request.user)

    if request.method == "POST" and not existing:
        form = ApplicationForm(request.POST)
        try:
            if form.is_valid():
                apply_to_job(job, request.user, form.cleaned_data["cover_letter"])
                messages.success(
                    request,
                    _("Application sent: the company has been notified."),
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
def job_manage(request, pk):
    """
    Company workspace for one offer: review applications (accept / decline),
    close the job.
    """
    job = get_object_or_404(Job.objects.select_related("published_by"), pk=pk)
    if job.published_by_id != request.user.pk and not request.user.is_superuser:
        raise PermissionDenied(_("Only the publishing company can manage this job."))

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
                    _("Decision recorded: the applicant has been notified."),
                )
            elif action == "close":
                close_job(job, request.user)
                messages.success(request, _("Job closed: it no longer accepts applications."))
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
