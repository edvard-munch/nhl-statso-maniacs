.PHONY: format lint check hooks hooks-run

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
