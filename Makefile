.PHONY: install db-up db-down db-wait migrate seed ingest-one ingest-all test lint format bootstrap clean

install:
	uv sync --extra dev

db-up:
	docker compose up -d postgres
	@$(MAKE) db-wait

db-down:
	docker compose down

db-wait:
	@echo "Waiting for Postgres..."
	@until docker exec jfb-postgres pg_isready -U jfb > /dev/null 2>&1; do sleep 0.5; done
	@echo "Postgres ready."

migrate:
	uv run alembic upgrade head

seed:
	uv run jfb seed load

ingest-one:
	uv run jfb ingest run --source greenhouse --company cohere

ingest-all:
	uv run jfb ingest all

classify:
	uv run jfb classify run

stats:
	uv run jfb stats

top:
	uv run jfb top

test:
	uv run pytest -v

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests

typecheck:
	uv run pyright

bootstrap: install db-up migrate seed
	@echo ""
	@echo "  Bootstrap complete."
	@echo "  Next: make ingest-one    (fetch Cohere's postings)"
	@echo "        make ingest-all    (run every configured ingester)"
	@echo "        make stats         (see what the DB contains)"
	@echo ""

clean:
	docker compose down -v
	rm -rf .venv artifacts resumes
