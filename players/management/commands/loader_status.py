"""Read loader run outcomes without acquiring a loader write lock."""

import json
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from players.models import LoaderRun

DEFAULT_LIMIT = 10
MAX_LIMIT = 1000


class Command(BaseCommand):
    help = "Show recent loader runs, their scope, progress and outcome"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
        parser.add_argument("--run-id", type=UUID)
        parser.add_argument("--json", action="store_true", dest="json_output")

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= MAX_LIMIT:
            raise CommandError(f"--limit must be between 1 and {MAX_LIMIT}")
        runs = LoaderRun.objects.all()
        if options["run_id"]:
            runs = runs.filter(pk=options["run_id"])
            if not runs.exists():
                raise CommandError("Loader run not found")
        values = list(runs.values()[: options["limit"]])
        if options["json_output"]:
            self.stdout.write(json.dumps(values, default=str, ensure_ascii=False))
        else:
            for row in values:
                self.stdout.write(json.dumps(row, default=str, ensure_ascii=False, sort_keys=True))
            if not values:
                self.stdout.write("No loader runs recorded")
