"""
Job board services: apply, decide, close. All state changes and the emails
that announce them live here so views and management commands share one
implementation (same pattern as certification.services).
"""

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from urbantrack.emails import absolute_url, send_branded_mail

from .models import ApplicationStatus, Job, JobApplication


class JobsError(Exception):
    """Domain error raised for invalid job-board transitions."""


def _send(subject, body, recipient_list, template, context=None):
    send_branded_mail(
        subject=subject,
        text=body,
        recipient_list=recipient_list,
        template=template,
        context=context,
    )


@transaction.atomic
def apply_to_job(job, applicant, cover_letter):
    """Expert applies to an open job; both parties get notified."""

    if job.published_by_id == applicant.pk:
        raise JobsError(_("You cannot apply to your own job offer."))
    if not job.is_open:
        raise JobsError(_("This job offer is closed to new applications."))
    if JobApplication.objects.filter(job=job, applicant=applicant).exists():
        raise JobsError(_("You already applied to this job."))

    application = JobApplication.objects.create(
        job=job, applicant=applicant, cover_letter=cover_letter
    )
    first_name = applicant.first_name or _("there")
    _send(
        _("Urban Track: application received"),
        _(
            "Hi %(first)s,\n\n"
            "Your application to “%(title)s” (%(org)s) has been sent.\n"
            "Track its status from your Urban Track dashboard.\n\n"
            "— Urban Track"
        )
        % {
            "first": first_name,
            "title": job.title,
            "org": job.published_by.organisation_name,
        },
        [applicant.email],
        template="emails/job_application_received.html",
        context={
            "heading": "Application received",
            "preheader": f"Your application to '{job.title}' has been sent.",
            "first": first_name,
            "title": job.title,
            "org": job.published_by.organisation_name,
            "my_applications_url": absolute_url("/jobs/mine/"),
        },
    )
    applicant_name = applicant.get_full_name() or applicant.username
    _send(
        _("Urban Track: new application for “%(title)s”") % {"title": job.title},
        _(
            "%(name)s (%(pid)s) just applied to “%(title)s”.\n"
            "Review it from your company dashboard:\n%(url)s\n\n— Urban Track"
        )
        % {
            "name": applicant_name,
            "pid": getattr(applicant.expert_profile, "professional_id", "") or "",
            "title": job.title,
            "url": absolute_url(f"/jobs/{job.pk}/manage/"),
        },
        [job.published_by.email],
        template="emails/job_new_application.html",
        context={
            "heading": "New application received",
            "preheader": f"{applicant_name} just applied to '{job.title}'.",
            "name": applicant_name,
            "pid": getattr(applicant.expert_profile, "professional_id", "") or "",
            "title": job.title,
            "manage_url": absolute_url(f"/jobs/{job.pk}/manage/"),
        },
    )
    return application


@transaction.atomic
def decide_application(application, actor, accept):
    """Company accepts or declines an application; expert is notified."""
    if application.job.published_by_id != actor.pk and not actor.is_superuser:
        raise JobsError(_("Only the publishing company can review applications."))
    if application.status != ApplicationStatus.PENDING:
        raise JobsError(_("This application was already reviewed."))

    application.status = ApplicationStatus.ACCEPTED if accept else ApplicationStatus.REJECTED
    application.decided_at = timezone.now()
    application.save(update_fields=["status", "decided_at"])

    if accept:
        body = _(
            "Congratulations %(first)s!\n\n"
            "Your application to “%(title)s” (%(org)s) has been ACCEPTED.\n"
            "The company will contact you at %(email)s to define the next steps.\n\n"
            "— Urban Track"
        )
    else:
        body = _(
            "Hi %(first)s,\n\n"
            "After careful review, your application to “%(title)s” "
            "(%(org)s) was not retained this time.\n"
            "Your certified profile keeps growing: new missions are posted regularly.\n\n"
            "— Urban Track"
        )
    first_name = application.applicant.first_name or _("there")
    _send(
        _("Urban Track: decision on your application"),
        body
        % {
            "first": first_name,
            "title": application.job.title,
            "org": application.job.published_by.organisation_name,
            "email": application.applicant.email,
        },
        [application.applicant.email],
        template="emails/job_decision.html",
        context={
            "heading": "Decision on your application",
            "preheader": f"Your application to '{application.job.title}' was reviewed.",
            "first": first_name,
            "accepted": accept,
            "title": application.job.title,
            "org": application.job.published_by.organisation_name,
            "email": application.applicant.email,
            "dashboard_url": absolute_url("/accounts/dashboard/"),
        },
    )
    return application


@transaction.atomic
def close_job(job, actor):
    """Stop accepting applications."""
    from .models import JobStatus

    if job.published_by_id != actor.pk and not actor.is_superuser:
        raise JobsError(_("Only the publishing company can close this job."))
    if job.status == JobStatus.CLOSED:
        raise JobsError(_("This job is already closed."))
    job.status = JobStatus.CLOSED
    job.save(update_fields=["status", "updated_at"])
    return job


def send_deadline_reminders(days_ahead=3):
    """
    Remind applicants whose pending application concerns a job closing within
    ``days_ahead`` days, and companies with unreviewed applications on jobs
    that close soon. Returns counts for the command output.
    """
    from .models import ApplicationStatus, JobStatus

    today = timezone.localdate()
    horizon = today + timezone.timedelta(days=days_ahead)
    experts_reminded = companies_reminded = 0

    closing = Job.objects.filter(
        status=JobStatus.OPEN, deadline__gte=today, deadline__lte=horizon
    ).select_related("published_by")

    for job in closing:
        pending = job.applications.filter(status=ApplicationStatus.PENDING).select_related(
            "applicant"
        )
        for application in pending:
            _send(
                _("Urban Track: reminder: “%(title)s” closes soon") % {"title": job.title},
                _(
                    "Hi %(first)s,\n\n"
                    "Your application to “%(title)s” is still under review and "
                    "the offer closes on %(deadline)s (%(days)s day(s)).\n"
                    "No action needed: we will email you the decision either way.\n\n"
                    "— Urban Track"
                )
                % {
                    "first": application.applicant.first_name or _("there"),
                    "title": job.title,
                    "deadline": job.deadline.strftime("%d %b %Y"),
                    "days": job.days_until_deadline,
                },
                [application.applicant.email],
                template="emails/job_deadline_expert.html",
                context={
                    "heading": "An offer closes soon",
                    "preheader": f"'{job.title}' closes on {job.deadline:%Y-%m-%d}.",
                    "first": application.applicant.first_name or _("there"),
                    "title": job.title,
                    "deadline": job.deadline.strftime("%d %b %Y"),
                    "days": job.days_until_deadline,
                    "job_url": absolute_url(f"/jobs/{job.pk}/"),
                },
            )
            experts_reminded += 1
        if pending:
            _send(
                _("Urban Track: %(count)s application(s) awaiting review")
                % {"count": pending.count()},
                _(
                    "The offer “%(title)s” closes on %(deadline)s and still has "
                    "%(count)s unreviewed application(s).\n"
                    "Review them from your dashboard.\n\n— Urban Track"
                )
                % {
                    "title": job.title,
                    "deadline": job.deadline.strftime("%d %b %Y"),
                    "count": pending.count(),
                },
                [job.published_by.email],
                template="emails/job_deadline_company.html",
                context={
                    "heading": "Applications awaiting review",
                    "preheader": f"'{job.title}' closes on {job.deadline:%Y-%m-%d}.",
                    "title": job.title,
                    "deadline": job.deadline.strftime("%d %b %Y"),
                    "count": pending.count(),
                    "manage_url": absolute_url(f"/jobs/{job.pk}/manage/"),
                },
            )
            companies_reminded += 1
    return {"experts_reminded": experts_reminded, "companies_reminded": companies_reminded}
