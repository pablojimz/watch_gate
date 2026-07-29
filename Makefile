.PHONY: install lint test run-demo

install:
	poetry install

lint:
	poetry run ruff check .
	poetry run ruff format --check .
	poetry run mypy
	poetry run lint-imports

test:
	poetry run pytest --cov --cov-report=term-missing

run-demo:
	poetry run watchgate analyze --base HEAD~1 --head HEAD
