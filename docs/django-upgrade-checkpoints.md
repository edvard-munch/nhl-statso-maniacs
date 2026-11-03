# Django/Python upgrade checkpoints

The upgrade is proceeding in small, reviewable steps. The current validated stack
is Python 3.12.16 / Django 4.2.30. Earlier checkpoints below retain their historical
results. Keep the interpreter pin accurate as the runtime changes.

## Checkpoint 1: Django 2.2.6 to 2.2.28

Status: implemented and validated locally on Python 3.7.17.

This checkpoint pinned Django 2.2.28. Other application dependencies and the
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

The project venv was updated to 2.2.28 at this checkpoint. To install the currently
pinned requirements in another checkout/environment:

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

## Checkpoint 3: Python 3.7.17 to 3.10.22

Status: implemented and validated locally, retaining Django 3.2.25. Python 3.10
is a temporary bridge, not the final runtime; its final patch is
[3.10.22](https://www.python.org/downloads/release/python-31022/), and it has reached
end of life. Continue to Django 4.2, then the Python 3.12 bridge and Django 5.2.

`.python-version` pins 3.10.22, Ruff targets `py310`, and CI reads the pin directly
with `setup-python`'s `python-version-file`. GitHub's
[interpreter manifest](https://github.com/actions/python-versions/blob/main/versions-manifest.json)
includes an Ubuntu 22.04 x64 build for this patch. Coverage artifacts are now named
`coverage-python310`. The working venv was recreated using the target interpreter;
the previous venv was preserved separately, and the application database was untouched.

### Dependency changes

| Component | Target | Reason |
| --- | --- | --- |
| Celery / Kombu / AMQP / Vine | 5.2.7 / 5.2.4 / 5.1.1 / 5.0.0 | Replace the Python 3.7-era task stack with a coherent Python 3.10-compatible set. |
| django-celery-results | 2.4.0 | Match Celery 5 and remove old imports of `celery.five` and `ugettext_lazy`. |
| psycopg2-binary | 2.9.10 | Use a driver with Python 3.10 wheels. |
| pytest / pytest-cov | 7.4.4 / 4.1.0 | Replace old assertion-rewriting/test tooling for the newer interpreter. |
| Pluggy / packaging | 1.3.0 / 23.2 | Meet the new pytest tooling's dependency constraints. |
| coverage | 7.2.7 | Explicitly retain the version used for earlier measured baselines. |

The bootstrap and pre-commit versions remain unchanged for this step. Celery's
[5.2 release notes](https://docs.celeryq.dev/en/v5.2.3/whatsnew-5.2.html) document
Python 3.10 support. These pins are a tested bridge, not the final dependency set.

### Validation and migration implications

- Fresh target installs and the recreated working venv pass `pip check`.
- System checks and model/migration drift checks pass.
- A disposable UTF-8 PostgreSQL 16 database was migrated and seeded under the
  previous Python 3.7 / Celery 4 environment, then upgraded under Python 3.10.
  All 13 player JSON fields, IDs, team links, user/profile identity/passwords,
  favorites and comparisons match before/after snapshots. Stored task IDs,
  status, result payloads, metadata, arguments and completion times also match;
  the new task creation timestamp is backfilled from completion time.
- django-celery-results migrations **0005 through 0011** apply successfully.
  They add worker/creation/periodic-task fields, group/chord tables and indexes,
  and **remove the old `TaskResult.hidden` column**. Task rows and result payloads
  survive; the removed soft-delete flag does not. No application migration is added.
- **414 offline tests pass**, 12 external checks are deselected, and combined
  coverage is **82.79%**, including through the managed push hook. Five new tests
  cover eager loader order/failure and database-backend result update/decoding.
  No broker or live loader is invoked. Broker/worker deployment checks remain
  separate from these offline tests.
- A fresh temporary checkout without a venv, `.env` or logs passes static checks,
  the full coverage gate and XML export. Workflow syntax passes actionlint.
  Hosted CI and the dependency graph must still be verified after pushing.

Remaining startup/test warnings concern Celery/Kombu's entry-point API and
django-pdb's `default_app_config`; resolve them during the following dependency
and Django 4.2 work. The 35% coverage gate and exclusions are unchanged. Coverage
denominators also vary across Python versions, so percentages are not an exact
cross-interpreter comparison.

### Recreate another Python 3.7 environment

Deactivate the old venv and move it outside the checkout before creating the new
`venv`. Installing packages into the old venv does not upgrade its interpreter.
With pyenv available, run from the project root:

```bash
pyenv install -s 3.10.22
python --version  # must report 3.10.22 from .python-version
python -m venv venv
source venv/bin/activate
python -m pip install -r requirements-bootstrap.txt
python -m pip install -r requirements.txt -r requirements-hooks.txt
python -m pip check
make hooks
```

Back up the application database, stop old Celery workers, inspect
`python manage.py migrate --plan`, then run `python manage.py migrate` before
restarting the app/workers with the new venv. Use dedicated test credentials for
`make hooks-run-push`. The local implementation only migrated disposable databases.

## Checkpoint 4: Django 3.2.25 to 4.2.30

Status: implemented and validated locally, retaining Python 3.10.22. Django 4.2
is another temporary checkpoint; the supported endpoint remains Django 5.2.
The [4.2.30 release notes](https://docs.djangoproject.com/en/4.2/releases/4.2.30/)
record the selected patch. The intervening
[4.0](https://docs.djangoproject.com/en/4.2/releases/4.0/),
[4.1](https://docs.djangoproject.com/en/4.2/releases/4.1/) and
[4.2](https://docs.djangoproject.com/en/4.2/releases/4.2/) notes were reviewed.

The framework pin moves to 4.2.30 and debug-toolbar to 4.4.6, which supports
Django 4.2's storage and form APIs. Other requirements and the interpreter pin
are unchanged. The existing crispy-forms Bootstrap 4 rendering passes the new
form tests, so a template-pack migration is deferred. Existing PostgreSQL JSON
fields and integer primary keys retain their definitions. Historical migration
imports remain intact.

### Compatibility changes and regressions

The navigation now submits logout through a CSRF-protected POST form, with the
existing return-page destination. The endpoint rejects GET with HTTP 405, keeps
the session intact on invalid CSRF, and refuses external redirect destinations.
This removes the app's reliance on GET logout, deprecated in Django 4.1 and removed
in Django 5.0. The navbar's search form was properly closed before the new logout
form. The button retains the existing navigation styling.

The explicit `USE_L10N=True` setting is removed: localization remains enabled by
default in 4.2 and is always enabled in Django 5. No deprecated-pytz compatibility
flag was enabled; Django uses its default zoneinfo implementation, while the two
explicit Pacific-date helpers retain their existing pytz behavior.

Nine new offline regressions check public auth-form rendering, registration and
profile creation, same-origin HTTPS login with real CSRF validation, profile form
rendering, POST logout/CSRF/session/redirect behavior, and development-home rendering
with the toolbar enabled. The development-server command also loads successfully.

### Validation

A disposable UTF-8 PostgreSQL 16 database was built and seeded under the committed
Django 3.2.25 code, then inspected under the target code. There are **no new
migration operations** for this checkpoint. System checks and model/migration drift
checks pass. Before/after snapshots preserve all 13 player JSON fields, primary
keys, team links, favorites, comparisons, user/profile identity and password
verification, plus task-result values and timestamps. The working venv is updated;
the application database was not accessed or migrated.

The full suite passes **423 offline tests**, with 12 external checks deselected
and **82.79% combined coverage**. The 35% gate and coverage exclusions are unchanged.
`pip check`, Ruff and formatting checks pass. Hosted results must still be inspected
after pushing.

Remaining test warnings are the Celery/Kombu entry-point deprecations and Django's
GET-logout warning from the intentional test proving GET is rejected. No warning
filter was added. The application navigation uses POST. Celery/dependency updates
remain part of the next Python bridge.

For another environment, activate its Python 3.10 venv, install the bootstrap and
application requirements, then run `pip check`, `manage.py check` and
`manage.py migrate --plan`. From the preceding checkpoint the plan is empty;
environments that skipped earlier checkpoints must apply their pending migrations.
Use the dedicated test configuration for local hooks.

## Checkpoint 5: Python 3.10.22 to 3.12.16

Status: implemented and validated locally, retaining Django 4.2.30. The
[Python 3.12.16 security release](https://www.python.org/downloads/release/python-31216/)
is pinned in `.python-version`; Ruff targets `py312`. CI reads the same pin and
exports `coverage-python312`. The
[GitHub interpreter manifest](https://github.com/actions/python-versions/blob/main/versions-manifest.json)
includes an Ubuntu 22.04 x64 build. The local interpreter was built from the
official source archive after verifying its published SHA-256 checksum.

### Dependency changes

The target was installed in isolated environments before recreating the working
venv. The old venv was preserved separately. The bootstrap keeps pip/wheel fixed
and updates setuptools to 75.8.0 for Python 3.12's removed import APIs.

| Component | Target | Reason |
| --- | --- | --- |
| ASGI adapter | asgiref 3.8.1 | Python 3.12-compatible Django runtime dependency. |
| Task stack | Celery 5.4.0, Kombu 5.3.7, AMQP 5.2.0, Billiard 4.2.1, Vine 5.1.0 | Python 3.12-compatible task execution and multiprocessing dependencies. |
| Task database backend | django-celery-results 2.5.1 | Match the newer runtime/task stack; existing backend regressions still pass. |
| Date/time dependencies | python-dateutil 2.9.0.post0, tzdata 2026.6 | Pin Celery's newly introduced dependencies; avoid a floating dateutil major version. |
| Native libraries | gevent 24.11.1, greenlet 3.1.1, Pillow 10.4.0, zope.event 5.0, zope.interface 7.2 | Python 3.12-compatible native builds/wheels. |
| HTTP stack | Requests 2.32.4, urllib3 2.5.0, six 1.17.0, certifi 2025.6.15, idna 3.10, charset-normalizer 3.4.2 | Replace removed import machinery in the old HTTP dependencies and keep their versions coherent. |
| Test tooling | coverage 7.6.12, pytest-django 4.8.0, py 1.11.0 | Python 3.12 tracing/collection support; the old `py` package failed with `AttributeError: __spec__`. |

The old urllib3 also failed with `ModuleNotFoundError: urllib3.packages.six.moves`
on Python 3.12. Both observed import failures were fixed before running the suite.
Other legacy dependencies remain for later review; this is not a full dependency
refresh or a new lockfile. Pre-commit retains its existing version and interface.
See [Celery 5.4's notes](https://docs.celeryq.dev/en/stable/history/whatsnew-5.4.html)
and the [gevent release history](https://docs.gevent.org/changelog.html).

### Validation

- The final requirements install successfully on Python 3.12.16 and pass `pip check`.
- System checks and model/migration drift checks pass; the migration plan is empty.
- A disposable UTF-8 PostgreSQL 16 database created/seeded under the preceding
  Python 3.10 checkpoint retains all 13 player JSON fields, primary keys, team
  links, saved memberships, user/profile identity and password verification,
  and task-result payloads/metadata/timestamps after the transition.
- **425 offline tests pass**, including through the managed push hook, with 12
  external tests deselected and **82.51% combined coverage**. Two new profile
  regressions verify valid PNG upload and
  account edits, and rejection of invalid image bytes without persisting edits.
  File writes stay within pytest's temporary media directory.
- Separate smoke checks exercise gevent jobs, a greenlet switch and Billiard's
  child-process pool. Existing Celery tests exercise eager task order/failure
  and database results without a broker. Hosted broker/worker deployment still
  requires its own check.
- A clean temporary checkout passes static checks, the complete coverage suite,
  development-server command loading and coverage XML export. Local validation
  does not establish that hosted CI passed.

The gate remains 35%, and measurement scope/exclusions are unchanged. The small
percentage change from 82.79% reflects the new interpreter/tracer's branch
denominator; it is not evidence of lost behavior coverage. Do not compare these
cross-interpreter percentages as identical measurements.

Remaining warnings concern pytz's deprecated UTC timestamp helper, old debug
`print(form)` calls in the profile view, and the intentional GET-logout rejection
test. Resolve the relevant form/dependency deprecations during the Django 5.2
step; no warning filters were added.

### Recreate another environment

Deactivate and move the old venv outside the checkout first. With pyenv available,
run from the project root:

```bash
pyenv install -s 3.12.16
python --version  # must report 3.12.16 from .python-version
python -m venv venv
source venv/bin/activate
python -m pip install -r requirements-bootstrap.txt
python -m pip install -r requirements.txt -r requirements-hooks.txt
python -m pip check
make hooks
python manage.py check
python manage.py migrate --plan
```

Restart application/Celery processes with the new venv. From the preceding
checkpoint there are no migrations; environments missing earlier checkpoints
still need their pending migrations applied. Run the local hook checks with the
dedicated test credentials. The application database was not accessed or migrated
during implementation.

## Next checkpoints

1. Move to Django 5.2 while retaining Python 3.12.
   Older framework/interpreter versions remain temporary checkpoints.

Follow the [roadmap](modernization-roadmap.md) and Django's
[upgrade guide](https://docs.djangoproject.com/en/3.2/howto/upgrade-version/): review
intervening release notes and deprecations, run tests and migration checks, then
record a working checkpoint before moving on. Remaining high-value regression
batches can accompany the upgrade when they protect affected behavior.

## Dependabot status

The earlier hosted graph rejected Python 3.7.17. The bridge now uses a tested
Python 3.12.16 interpreter, and test CI reads `.python-version` directly. This
addresses that run's version restriction in the repository; it does not prove
the hosted service succeeds. Push and inspect both the offline-test workflow and
the separate dependency graph. No security feature was disabled and no version
was misreported. Other dependency findings remain separate upgrade work.
