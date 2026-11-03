.PHONY: format lint check hooks hooks-run hooks-run-push test test-cov test-ci

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
