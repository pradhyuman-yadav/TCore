.PHONY: dev prod down test migrate logs shell-db

# ── Local development ─────────────────────────────────────────────────────────
dev:
	docker compose up --build

dev-bg:
	docker compose up --build -d

down:
	docker compose down

# ── Production ────────────────────────────────────────────────────────────────
prod:
	docker compose -f docker-compose.prod.yml up --build -d

prod-down:
	docker compose -f docker-compose.prod.yml down

prod-logs:
	docker compose -f docker-compose.prod.yml logs -f

# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	docker compose exec backend uv run alembic upgrade head

shell-db:
	docker compose exec timescaledb psql -U $${DB_USER} -d tradecore

# ── Tests (requires running DB) ───────────────────────────────────────────────
test:
	cd backend && .\.venv\Scripts\python.exe -m pytest -v

test-e2e:
	cd backend && .\.venv\Scripts\python.exe -m pytest tests/test_e2e.py -v

test-scaffold:
	cd backend && .\.venv\Scripts\python.exe -m pytest tests/test_scaffold.py -v

# ── Auth setup ────────────────────────────────────────────────────────────────
auth:
	powershell -ExecutionPolicy Bypass -File scripts/setup_claude_auth.ps1

# ── Logs ─────────────────────────────────────────────────────────────────────
logs:
	docker compose logs -f backend

logs-all:
	docker compose logs -f
