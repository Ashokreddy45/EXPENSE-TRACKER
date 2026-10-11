from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone

from home.models import Goal, GoalReminder


class Command(BaseCommand):
    help = "Send one-time email reminders for upcoming financial goals."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview eligible reminders without sending emails or saving records.",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        dry_run = options["dry_run"]

        if not dry_run and not (
            settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD
        ):
            self.stderr.write(
                self.style.ERROR(
                    "Email credentials are missing. Configure "
                    "EMAIL_HOST_USER and EMAIL_HOST_PASSWORD first."
                )
            )
            return

        reminder_days = {
            7: "7_day",
            1: "1_day",
        }

        sent_count = 0
        skipped_count = 0
        error_count = 0

        goals = Goal.objects.select_related("user").filter(
            deadline__isnull=False,
            deadline__gte=today,
        ).order_by("deadline", "id")

        for goal in goals:
            target = goal.target_amount or 0
            saved = goal.current_amount or 0

            if saved >= target:
                continue

            days_until_deadline = (goal.deadline - today).days
            reminder_type = reminder_days.get(days_until_deadline)

            if not reminder_type:
                continue

            if not goal.user.email:
                self.stdout.write(
                    f"Skipped goal #{goal.pk}: user has no email address."
                )
                skipped_count += 1
                continue

            if GoalReminder.objects.filter(
                goal=goal,
                reminder_type=reminder_type,
            ).exists():
                continue

            if dry_run:
                self.stdout.write(
                    f"[DRY RUN] Would send {days_until_deadline}-day reminder "
                    f"for '{goal.description}' to {goal.user.email}."
                )
                sent_count += 1
                continue

            subject = (
                f"FinTrack reminder: {goal.description} "
                f"is due in {days_until_deadline} day"
                f"{'s' if days_until_deadline != 1 else ''}"
            )

            remaining = max(target - saved, 0)
            message = (
                f"Hello {goal.user.username},\n\n"
                f"This is a reminder about your financial goal: "
                f"{goal.description}.\n\n"
                f"Target amount: ₹{target:,.2f}\n"
                f"Current savings: ₹{saved:,.2f}\n"
                f"Amount remaining: ₹{remaining:,.2f}\n"
                f"Deadline: {goal.deadline:%d %b %Y}\n\n"
                f"Open FinTrack to review your savings plan.\n\n"
                "This is an automated reminder from FinTrack."
            )

            try:
                # Record only after email delivery is accepted by the backend.
                with transaction.atomic():
                    if GoalReminder.objects.filter(
                        goal=goal,
                        reminder_type=reminder_type,
                    ).exists():
                        continue

                    email_sent = send_mail(
                        subject=subject,
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[goal.user.email],
                        fail_silently=False,
                    )

                    if email_sent != 1:
                        raise RuntimeError("Email backend did not send the email.")

                    GoalReminder.objects.create(
                        goal=goal,
                        reminder_type=reminder_type,
                    )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Sent {days_until_deadline}-day reminder for "
                        f"'{goal.description}' to {goal.user.email}."
                    )
                )
                sent_count += 1

            except Exception as exc:
                error_count += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"Failed reminder for goal #{goal.pk}: {exc}"
                    )
                )

        prefix = "Dry run complete" if dry_run else "Reminder run complete"
        self.stdout.write(
            f"{prefix}. Eligible/sent: {sent_count}; "
            f"skipped: {skipped_count}; errors: {error_count}."
        )
