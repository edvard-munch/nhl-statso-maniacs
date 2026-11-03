.PHONY: format lint check hooks hooks-run test test-cov test-ci

format:
	python -m ruff format .

lint:
	python -m ruff check .

check:
	python -m ruff check .
	python -m ruff format --check .

hooks:
	pre-commit install

hooks-run:
	pre-commit run --all-files

test:
	python -m pytest -c players/tests/pytest.ini players/tests

test-cov:
	python -m pytest -c players/tests/pytest.ini --cov=players --cov-config=.coveragerc --cov-report=term-missing players/tests

test-ci:
	python -m pytest -c players/tests/pytest.ini --cov=players --cov-config=.coveragerc --cov-report=term-missing --cov-fail-under=35 players/tests
