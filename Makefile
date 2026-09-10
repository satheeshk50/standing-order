# Convenience targets. Windows users without make: the commands are short
# enough to paste — see the README.

PY := backend/.venv/Scripts/python.exe
ifeq ($(OS),)
  PY := backend/.venv/bin/python
endif

.PHONY: help infra infra-down install migrate seed api worker web reset demo

help:
	@echo "make infra    - start Postgres + Temporal (docker)"
	@echo "make install  - create venv, install backend + frontend deps"
	@echo "make migrate  - apply database migrations"
	@echo "make seed     - insert the supervisor templates"
	@echo "make api      - run FastAPI on :8000"
	@echo "make worker   - run the Temporal worker"
	@echo "make web      - run Next.js on :3000"
	@echo "make demo     - drive a scripted order through a live run"

infra:
	docker compose up -d postgres temporal

infra-down:
	docker compose down

install:
	cd backend && python -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements.txt
	cd frontend && npm install

migrate:
	cd backend && .venv/Scripts/python.exe -m alembic upgrade head

seed:
	cd backend && .venv/Scripts/python.exe -m app.seed

api:
	cd backend && .venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000

worker:
	cd backend && .venv/Scripts/python.exe -m app.worker

web:
	cd frontend && npm run dev

demo:
	cd backend && .venv/Scripts/python.exe ../scripts/simulate_order.py --scenario delayed_delivery

reset:
	docker compose down -v
