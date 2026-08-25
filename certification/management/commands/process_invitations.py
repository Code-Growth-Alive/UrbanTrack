"""
Scheduled maintenance of expert invitations (Epic 5, rule 6).

Replaces the Celery-Beat task mandated by the original spec with a
synchronous management command (project decision: no Celery/Redis). Wire it
to cron, e.g. daily at 08:00 UTC:

    0 8 * * * cd /srv/urbantrack && ./env/bin/python manage.py process_invitations
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from certification.models import ContributionStatus, ExpertInvitation
from certification.services import (
    InvalidTransitionError,
    expire_stale_invitations,
    send_invitation_reminder,
)


class Command(BaseCommand):
    help = (
        "Send due invitation reminders (capped) and mark overdue invitations "
        "as expired. Intended for periodic execution via cron."
    )

    def handle(self, *args, **options):
        now = timezone.now()

        # 1. Reminders: active invitations still awaiting an answer, past the
        #    silence threshold, under the reminder cap.
        due = ExpertInvitation.objects.filter(
            expires_at__gt=now,
            reminder_count__lt=settings.INVITATION_MAX_REMINDERS,
            sent_at__lte=now - timedelta(days=settings.INVITATION_REMINDER_AFTER_DAYS),
            contribution__status__in=ContributionStatus.actionable(),
        ).exclude(status="expired")

        reminded = 0
        for invitation in due:
            try:
                send_invitation_reminder(invitation)
                reminded += 1
            except InvalidTransitionError:
                continue

        # 2. Expiry: every overdue non-expired invitation flips to expired.
        expired = expire_stale_invitations(now)

        self.stdout.write(
            self.style.SUCCESS(
                f"process_invitations: {reminded} reminder(s) sent, "
                f"{expired} invitation(s) expired."
            )
        )
