.PHONY: format lint check hooks hooks-run

format:
	python -m ruff format .

lint:
	python -m ruff check .

check:
	python -m ruff check .
	python -m ruff format --check .

hooks:
	python -m pre_commit install

hooks-run:
	python -m pre_commit run --all-files
