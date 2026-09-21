"""
Job board services: apply, decide, close. All state changes and the emails
that announce them live here so views and management commands share one
implementation (same pattern as certification.services).
"""

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from main.emails import absolute_url, send_branded_mail

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
        raise JobsError(_("Vous ne pouvez pas candidater à votre propre offre de mission."))
    if not job.is_open:
        raise JobsError(_("Cette offre de mission est clôturée aux nouvelles candidatures."))
    if JobApplication.objects.filter(job=job, applicant=applicant).exists():
        raise JobsError(_("Vous avez déjà candidaté à cette mission."))

    application = JobApplication.objects.create(
        job=job, applicant=applicant, cover_letter=cover_letter
    )
    first_name = applicant.first_name or _("à vous")
    _send(
        _("Urban Track : candidature reçue"),
        _(
            "Bonjour %(first)s,\n\n"
            "Votre candidature à « %(title)s » (%(org)s) a été envoyée.\n"
            "Suivez son statut depuis votre tableau de bord Urban Track.\n\n"
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
            "heading": "Candidature reçue",
            "preheader": f"Votre candidature à « {job.title} » a été envoyée.",
            "first": first_name,
            "title": job.title,
            "org": job.published_by.organisation_name,
            "my_applications_url": absolute_url("/jobs/mine/"),
        },
    )
    applicant_name = applicant.get_full_name() or applicant.username
    _send(
        _("Urban Track : nouvelle candidature pour « %(title)s »") % {"title": job.title},
        _(
            "%(name)s (%(pid)s) vient de candidater à « %(title)s ».\n"
            "Examinez-la depuis votre tableau de bord de structure :\n%(url)s\n\n— Urban Track"
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
            "heading": "Nouvelle candidature reçue",
            "preheader": f"{applicant_name} vient de candidater à « {job.title} ».",
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
        raise JobsError(
            _("Seule la structure qui a publié la mission peut examiner les candidatures.")
        )
    if application.status != ApplicationStatus.PENDING:
        raise JobsError(_("Cette candidature a déjà été examinée."))

    application.status = ApplicationStatus.ACCEPTED if accept else ApplicationStatus.REJECTED
    application.decided_at = timezone.now()
    application.save(update_fields=["status", "decided_at"])

    if accept:
        body = _(
            "Félicitations %(first)s !\n\n"
            "Votre candidature à « %(title)s » (%(org)s) a été ACCEPTÉE.\n"
            "La structure vous contactera à %(email)s pour définir les prochaines étapes.\n\n"
            "— Urban Track"
        )
    else:
        body = _(
            "Bonjour %(first)s,\n\n"
            "Après un examen attentif, votre candidature à « %(title)s » "
            "(%(org)s) n'a pas été retenue cette fois.\n"
            "Votre profil certifié continue d'évoluer : de nouvelles missions sont"
                " publiées régulièrement.\n\n"
            "— Urban Track"
        )
    first_name = application.applicant.first_name or _("à vous")
    _send(
        _("Urban Track : décision sur votre candidature"),
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
            "heading": "Décision sur votre candidature",
            "preheader": f"Votre candidature à « {application.job.title} » a été examinée.",
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
        raise JobsError(_("Seule la structure qui a publié la mission peut la clôturer."))
    if job.status == JobStatus.CLOSED:
        raise JobsError(_("Cette mission est déjà clôturée."))
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
                _("Urban Track : rappel : « %(title)s » clôture bientôt") % {"title": job.title},
                _(
                    "Bonjour %(first)s,\n\n"
                    "Votre candidature à « %(title)s » est toujours en cours d'examen et "
                    "l'offre clôture le %(deadline)s (%(days)s jour(s)).\n"
                    "Aucune action requise : nous vous enverrons par email"
                    " la décision dans tous les cas.\n\n"
                    "— Urban Track"
                )
                % {
                    "first": application.applicant.first_name or _("à vous"),
                    "title": job.title,
                    "deadline": job.deadline.strftime("%d %b %Y"),
                    "days": job.days_until_deadline,
                },
                [application.applicant.email],
                template="emails/job_deadline_expert.html",
                context={
                    "heading": "Une offre clôture bientôt",
                    "preheader": f"« {job.title} » clôture le {job.deadline:%Y-%m-%d}.",
                    "first": application.applicant.first_name or _("à vous"),
                    "title": job.title,
                    "deadline": job.deadline.strftime("%d %b %Y"),
                    "days": job.days_until_deadline,
                    "job_url": absolute_url(f"/jobs/{job.pk}/"),
                },
            )
            experts_reminded += 1
        if pending:
            _send(
                _("Urban Track : %(count)s candidature(s) en attente d'examen")
                % {"count": pending.count()},
                _(
                    "L'offre « %(title)s » clôture le %(deadline)s et compte encore "
                    "%(count)s candidature(s) non examinée(s).\n"
                    "Examinez-les depuis votre tableau de bord.\n\n— Urban Track"
                )
                % {
                    "title": job.title,
                    "deadline": job.deadline.strftime("%d %b %Y"),
                    "count": pending.count(),
                },
                [job.published_by.email],
                template="emails/job_deadline_company.html",
                context={
                    "heading": "Candidatures en attente d'examen",
                    "preheader": f"« {job.title} » clôture le {job.deadline:%Y-%m-%d}.",
                    "title": job.title,
                    "deadline": job.deadline.strftime("%d %b %Y"),
                    "count": pending.count(),
                    "manage_url": absolute_url(f"/jobs/{job.pk}/manage/"),
                },
            )
            companies_reminded += 1
    return {"experts_reminded": experts_reminded, "companies_reminded": companies_reminded}
