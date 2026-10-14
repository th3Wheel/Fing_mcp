.PHONY: install test lint format manifest run run-http docker-test

install:
	pip install -r requirements-dev.txt

test:
	pytest -v --tb=short

lint:
	ruff check .
	ruff format --check .
	python scripts/gen_manifest.py --check

format:
	ruff format .
	ruff check --fix .

manifest:
	python scripts/gen_manifest.py

run:
	python server.py

run-http:
	MCP_TRANSPORT=http python server.py

docker-test:
	docker compose -f docker-compose.test.yml run --rm --build test
