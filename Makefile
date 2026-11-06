.PHONY: sync lock-check requirements requirements-check format lint check hooks hooks-run hooks-run-push test test-cov test-ci test-browser test-external update-daily update-all update-history

.DEFAULT_GOAL := format

UV ?= uv
UV_RUN = $(UV) run --locked
PYTHON ?= $(UV_RUN) python

sync:
	$(UV) sync --locked

lock-check:
	$(UV) lock --check

requirements:
	$(UV_RUN) python scripts/export_requirements.py

requirements-check:
	$(UV_RUN) python scripts/export_requirements.py --check

format:
	$(UV_RUN) python -m ruff format .

lint:
	$(UV_RUN) python -m ruff check .

check:
	$(UV_RUN) python -m ruff check .
	$(UV_RUN) python -m ruff format --check .

hooks:
	$(UV_RUN) python -m pre_commit install --hook-type pre-commit --hook-type pre-push

hooks-run:
	$(UV_RUN) python -m pre_commit run --all-files --hook-stage commit

hooks-run-push:
	$(UV_RUN) python -m pre_commit run --all-files --hook-stage push

test:
	$(UV_RUN) python -m pytest -c players/tests/pytest.ini players/tests

test-cov:
	$(UV_RUN) python -m pytest -c players/tests/pytest.ini --cov=players --cov-config=.coveragerc --cov-report=term-missing players/tests

test-ci:
	$(UV_RUN) python -m pytest -c players/tests/pytest.ini --cov=players --cov-config=.coveragerc --cov-report=term-missing --cov-fail-under=35 players/tests

# Uses the same dedicated test configuration as local hooks.
test-browser:
	$(UV_RUN) python scripts/run_hook_tests.py --browser

# Opt-in read-only NHL contracts; never part of normal tests, hooks or CI.
test-external:
	$(UV_RUN) python -m pytest -c players/tests/pytest.ini -m "external and not browser" --maxfail=1 players/tests/integration/tests_external_api_*.py

# Keep stages in one recipe so even make -j runs each loader in order and stops on error.
update-daily:
	$(PYTHON) manage.py upd_pls
	$(PYTHON) manage.py upd_pls_tot --mode=current
	$(PYTHON) manage.py upd_gms

# All routine stages, including weekly team metadata; historical backfill stays explicit.
update-all:
	$(PYTHON) manage.py upd_tms
	$(PYTHON) manage.py upd_pls
	$(PYTHON) manage.py upd_pls_tot --mode=current
	$(PYTHON) manage.py upd_gms

# Occasional historical refresh; keep heavier landing calls out of routine updates.
update-history:
	$(PYTHON) manage.py upd_pls_tot --mode=full
