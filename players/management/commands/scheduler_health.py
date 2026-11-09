"""Read-only saved-state health suitable for terminal use and monitoring."""

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from django.utils import timezone

from players import scheduler_health as health

EXIT_CODES = {"healthy": 0, "unhealthy": 1, "disabled": 2, "unknown": 3}


class Command(BaseCommand):
    help = "Check saved scheduler health without writing records or contacting services"
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="json_output")
        parser.add_argument("--grace-seconds", type=int, default=health.DEFAULT_GRACE_SECONDS)
        parser.add_argument("--max-run-seconds", type=int, default=health.DEFAULT_MAX_RUN_SECONDS)
        parser.add_argument(
            "--failure-lookback-hours", type=int, default=health.DEFAULT_LOOKBACK_HOURS
        )
        parser.add_argument("--limit", type=int, default=health.DEFAULT_LIMIT)

    def handle(self, *args, **options):
        for name, minimum, maximum in (
            ("grace_seconds", 0, health.MAX_THRESHOLD_SECONDS),
            ("max_run_seconds", 1, health.MAX_THRESHOLD_SECONDS),
            ("failure_lookback_hours", 1, health.MAX_LOOKBACK_HOURS),
            ("limit", 1, health.MAX_LIMIT),
        ):
            if not minimum <= options[name] <= maximum:
                raise CommandError(
                    f"--{name.replace('_', '-')} must be between {minimum} and {maximum}",
                    returncode=EXIT_CODES["unknown"],
                )
        try:
            result = health.report(
                timezone.now(),
                grace_seconds=options["grace_seconds"],
                max_run_seconds=options["max_run_seconds"],
                lookback_hours=options["failure_lookback_hours"],
                limit=options["limit"],
            )
        except DatabaseError:
            result = {
                "schema_version": health.SCHEMA_VERSION,
                "status": "unknown",
                "checked_at": timezone.now(),
                "issues": [
                    {
                        "code": "database_unavailable",
                        "message": "Unable to read scheduler tables; check database connectivity and applied migrations.",
                    }
                ],
            }
        if options["json_output"]:
            self.stdout.write(json.dumps(result, default=str, ensure_ascii=False))
        else:
            self.stdout.write(
                f"Scheduler: {result['status'].upper()} (saved database state only; services not probed)"
            )
            if result["status"] == "disabled":
                self.stdout.write("Scheduling is disabled; database health checks were skipped.")
            for name, job in result.get("jobs", {}).items():
                self.stdout.write(f"{name}: " + json.dumps(job, default=str, ensure_ascii=False))
            for name in (
                "cooldown_until",
                "cooldown_active",
                "running_count",
                "long_running_count",
                "unresolved_failure_count",
                "running",
                "recent_failures",
            ):
                if name in result:
                    self.stdout.write(
                        f"{name}: " + json.dumps(result[name], default=str, ensure_ascii=False)
                    )
            for issue in result["issues"]:
                self.stdout.write("Issue: " + json.dumps(issue))
        code = EXIT_CODES[result["status"]]
        if code:
            raise CommandError(f"Scheduler health: {result['status']}", returncode=code)
