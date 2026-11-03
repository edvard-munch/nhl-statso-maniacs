"""Existing PostgreSQL JSON and saved players survive the core JSONField migration."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]

BEFORE = [("players", "0046_auto_20260416_1420")]
AFTER = [("players", "0047_use_core_jsonfield")]


def test_core_jsonfield_migration_preserves_player_data_and_memberships():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(BEFORE)
        old_apps = executor.loader.project_state(BEFORE).apps
        user = old_apps.get_model("auth", "User").objects.create(username="json-upgrade-user")
        expected = {}
        for model_name in ("Skater", "Goalie"):
            model = old_apps.get_model("players", model_name)
            fields = {
                field.name: (
                    None
                    if field.name == "proj_stats"
                    else {"field": field.name, "nested": [0, False, None, {"city": "München"}]}
                )
                for field in model._meta.fields
                if field.get_internal_type() == "JSONField"
            }
            fields["sbs_stats"] = [{"season": "2026-27", "gamesPlayed": 3, "goals": 1}]
            player = model.objects.create(
                nhl_id=900001, name=model_name, birth_date="2000-01-01", games=3, **fields
            )
            player.favoriting.add(user)
            player.comparing.add(user)
            expected[model_name] = (player.pk, fields)

        executor = MigrationExecutor(connection)
        executor.migrate(AFTER)
        new_apps = executor.loader.project_state(AFTER).apps
        for model_name, (pk, fields) in expected.items():
            model = new_apps.get_model("players", model_name)
            player = model.objects.get(pk=pk)
            assert {name: getattr(player, name) for name in fields} == fields
            assert list(player.favoriting.values_list("pk", flat=True)) == [user.pk]
            assert list(player.comparing.values_list("pk", flat=True)) == [user.pk]
            assert model.objects.filter(sbs_stats__contains=[{"season": "2026-27"}]).exists()
    finally:
        # Other tests must see the complete schema even if this assertion fails.
        MigrationExecutor(connection).migrate(latest)
