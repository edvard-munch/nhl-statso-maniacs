# Django/Python upgrade checkpoints

The upgrade is proceeding in small, reviewable steps. Dependency-graph generation
currently rejects the real Python 3.7.17 pin. Keep that pin accurate while moving
the framework and interpreter through the validated checkpoints below.

## Checkpoint 1: Django 2.2.6 to 2.2.28

Status: implemented and validated locally on Python 3.7.17.

`requirements.txt` now pins Django 2.2.28. Other application dependencies and the
interpreter pin are unchanged. This establishes the 2.2 patch baseline before the
3.x compatibility work. Django 2.2 is unsupported; this is a temporary upgrade
checkpoint, not the final supported stack. See the official
[2.2.28 release notes](https://docs.djangoproject.com/en/2.2/releases/2.2.28/).

### Validation

A disposable PostgreSQL 16 cluster was used for both versions. No application
database was connected to or migrated.

| Check | Django 2.2.6 | Django 2.2.28 |
| --- | --- | --- |
| `manage.py check` | No issues | No issues |
| `manage.py makemigrations --check --dry-run` | No changes detected | No changes detected |
| Apply existing migrations | Applied successfully to the isolated base database | No additional migrations to apply |
| `manage.py migrate --plan` after application | No planned operations | No planned operations |

The target also passes **408 offline tests**, with 12 external tests deselected,
**82.59% combined coverage** and the unchanged 35% coverage gate. `pip check`
reports no broken requirements. This rehearsal covers a database built from
migrations; a representative application-data copy remains part of later upgrade
validation. Existing loader/view persistence tests use their synthetic records.

The local project venv has been updated to 2.2.28. For another checkout/environment:

```bash
source venv/bin/activate
python -m pip install -r requirements-bootstrap.txt
python -m pip install -r requirements.txt
python -m pip check
python -m django --version
```

Before committing, run the local hooks with the dedicated test configuration.
CI now logs the Django version and runs system/model-migration checks before the
offline coverage suite. Tests still use real migrations; no migration file was
added by this checkpoint.

## Checkpoint 2: Django 2.2.28 to 3.2.25

Status: implemented and validated locally on Python 3.7.17. Django 3.2 is also
unsupported and serves only as the next upgrade checkpoint.

Compatible dependencies are pinned to crispy-forms 1.14.0, debug-toolbar 3.8.1,
django-extensions 3.2.3, django-storages 1.13.2 and pytest-django 4.5.2. The other
requirements and Python pin are unchanged. The project venv uses this set and
`pip check` passes. Celery 4.3 still requires the pinned pip version because its
dependency metadata is deprecated; its modernization remains separate work.
An explicit warnings-enabled startup audit also finds deprecated `ugettext_lazy`
calls in django-celery-results, automatic app-config notices in that package and
django-pdb, and Kombu's old entry-point API. These third-party warnings must be
resolved before the Django 4.2 step; they are not suppressed by this checkpoint.

`DEFAULT_AUTO_FIELD` explicitly preserves existing integer primary keys. Current
models use Django's core `models.JSONField`, and regex URL routes use `re_path`.
Historical migrations retain their original imports. Migration
`players.0047_use_core_jsonfield` updates all 13 skater/goalie JSON field definitions;
`sqlmigrate` confirms it emits no column/data changes on PostgreSQL. Django also
adds `auth.0012_alter_user_first_name_max_length` (first names allow 150 characters).
See the [3.1 JSONField notes](https://docs.djangoproject.com/en/3.1/releases/3.1/)
and [3.2 upgrade notes](https://docs.djangoproject.com/en/3.2/releases/3.2/).

### Migration and data rehearsal

A disposable UTF-8 PostgreSQL 16 database was created using the committed Django
2.2.28 code and its real migrations. Synthetic users/profiles, skaters, goalies,
teams, favorites and comparisons were inserted before applying the target code.
Before/after snapshots match for all 13 JSON fields (including nested Unicode,
nulls, booleans and averages), primary keys, team links, saved memberships and
user/profile identity and password verification. System checks and model/migration
drift checks pass; after applying the two migrations no operations remain.
The application database was not accessed or migrated. A permanent migration
regression also verifies JSON values, saved memberships and JSON containment
queries against the real test schema.

The full push-stage hook passes **409 offline tests**, with 12 external checks
deselected and **82.58% combined coverage**, using the updated project venv and
a disposable PostgreSQL database. The 35% gate and coverage scope are unchanged.
Ruff and formatting checks pass. These are local results; a hosted run of this
checkpoint must still be checked after pushing.

### Apply this checkpoint to another environment

Back up the application database as usual, then from the project root:

```bash
source venv/bin/activate
python -m pip install -r requirements-bootstrap.txt
python -m pip install -r requirements.txt
python -m pip check
python manage.py check
python manage.py migrate --plan
python manage.py migrate
```

Installing requirements alone does not apply migrations. The local implementation
updated the venv but intentionally left the application database untouched.

## Next checkpoints

1. Establish the compatible Python 3.10 bridge separately, adjusting dependencies
   and test tooling as required. Recheck the dependency graph after that change.
2. Continue through Django 4.2, the planned Python 3.12 bridge, and Django 5.2.
   Older framework/interpreter versions remain temporary checkpoints.

Follow the [roadmap](modernization-roadmap.md) and Django's
[upgrade guide](https://docs.djangoproject.com/en/3.2/howto/upgrade-version/): review
intervening release notes and deprecations, run tests and migration checks, then
record a working checkpoint before moving on. Remaining high-value regression
batches can accompany the upgrade when they protect affected behavior.

## Dependabot status

This checkpoint does **not** resolve the failing hosted dependency-graph job:
Python is still 3.7.17, which that service no longer supports. Our test CI is a
separate workflow and supports the current baseline. No security feature was
disabled and no interpreter version was misreported to make the graph job pass.
The runtime transition must be validated before updating `.python-version` and CI.
