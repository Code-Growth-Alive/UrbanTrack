"""Daily job-board maintenance: deadline reminders for pending applications."""

from django.core.management.base import BaseCommand

from jobs.services import send_deadline_reminders


class Command(BaseCommand):
    help = (
        "Remind applicants and companies about pending applications on job "
        "offers closing within the next few days. Schedule daily via cron."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=3,
            help="Reminder horizon in days before the deadline (default: 3).",
        )

    def handle(self, *args, **options):
        stats = send_deadline_reminders(days_ahead=options["days"])
        self.stdout.write(
            self.style.SUCCESS(
                "job reminders sent: %(experts)d expert(s), %(companies)d company(ies)"
                % {
                    "experts": stats["experts_reminded"],
                    "companies": stats["companies_reminded"],
                }
            )
        )
