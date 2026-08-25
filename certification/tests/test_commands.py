"""
Tests of the ``process_invitations`` command (Epic 5, rule 6): capped
reminders after the silence threshold, then expiry of overdue invitations.
"""

from datetime import timedelta

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from projects.services import publish_project
from projects.tests.test_models import make_company, make_project

from ..models import InvitationStatus
from ..services import declare_contributor


class ProcessInvitationsCommandTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.project = make_project(self.company)
        self.contribution = declare_contributor(
            self.project,
            email="slow@example.com",
            role_type="specialist",
            contribution_bullets="Did the analysis",
            added_by=self.company,
        )
        publish_project(self.project)
        self.invitation = self.contribution.invitations.get()
        mail.outbox = []

    def age(self, **kwargs):
        """Backdate the invitation as if it had been sent earlier."""
        self.invitation.sent_at = timezone.now() - timedelta(**kwargs)
        self.invitation.save(update_fields=["sent_at"])

    def test_no_reminder_before_threshold(self):
        self.age(days=2)  # threshold is 5 days
        call_command("process_invitations", verbosity=0)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.invitation.reminder_count, 0)

    def test_reminder_sent_after_threshold_and_capped_at_two(self):
        self.age(days=6)
        call_command("process_invitations", verbosity=0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("[Urban Track] Reminder", mail.outbox[0].subject)
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.reminder_count, 1)

        # Second reminder on the next run...
        self.age(days=12)
        call_command("process_invitations", verbosity=0)
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.reminder_count, 2)

        # ...then the budget is exhausted.
        mail.outbox.clear()
        call_command("process_invitations", verbosity=0)
        self.assertEqual(len(mail.outbox), 0)
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.reminder_count, 2)

    def test_overdue_invitation_is_expired(self):
        from datetime import timedelta as td

        self.invitation.expires_at = timezone.now() - td(days=1)
        self.invitation.save(update_fields=["expires_at"])
        call_command("process_invitations", verbosity=0)
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, InvitationStatus.EXPIRED)

    def test_confirmed_contribution_never_gets_reminded(self):
        from accounts.models import User
        from certification.services import confirm_as_is

        expert = User.objects.create_user(
            username="slow",
            email="slow@example.com",
            password="S3cret!pass",
            role="expert",
        )
        # Simulate a late signup + confirmation.
        self.contribution.expert = expert
        self.contribution.save(update_fields=["expert"])
        confirm_as_is(self.contribution, expert)
        mail.outbox.clear()

        self.age(days=10)
        call_command("process_invitations", verbosity=0)
        self.assertEqual(len(mail.outbox), 0)
