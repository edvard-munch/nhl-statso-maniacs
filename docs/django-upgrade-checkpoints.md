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

## Next checkpoints

1. Inventory dependencies and removed/deprecated APIs for Django 3.0/3.1/3.2,
   then move to the Django 3.2 checkpoint while keeping Python 3.7 for that change.
2. Establish the compatible Python 3.10 bridge separately, adjusting dependencies
   and test tooling as required. Recheck the dependency graph after that change.
3. Continue through Django 4.2, the planned Python 3.12 bridge, and Django 5.2.
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
