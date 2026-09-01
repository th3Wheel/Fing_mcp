.PHONY: install test lint format

install:
	pip install -r requirements-dev.txt

test:
	pytest tests/ -v --tb=short

lint:
	ruff check .

format:
	ruff format .
