.PHONY: format lint check hooks hooks-run hooks-run-push test test-cov test-ci test-browser update-daily update-all

PYTHON ?= python

format:
	python -m ruff format .

lint:
	python -m ruff check .

check:
	python -m ruff check .
	python -m ruff format --check .

hooks:
	python -m pre_commit install --hook-type pre-commit --hook-type pre-push

hooks-run:
	python -m pre_commit run --all-files --hook-stage commit

hooks-run-push:
	python -m pre_commit run --all-files --hook-stage push

test:
	python -m pytest -c players/tests/pytest.ini players/tests

test-cov:
	python -m pytest -c players/tests/pytest.ini --cov=players --cov-config=.coveragerc --cov-report=term-missing players/tests

test-ci:
	python -m pytest -c players/tests/pytest.ini --cov=players --cov-config=.coveragerc --cov-report=term-missing --cov-fail-under=35 players/tests

# Uses the same dedicated test configuration as local hooks.
test-browser:
	python scripts/run_hook_tests.py --browser

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
