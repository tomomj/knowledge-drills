SHELL := /bin/sh

BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000
FRONTEND_HOST ?= 127.0.0.1
FRONTEND_PORT ?= 5173
PORT ?= 8080

export UV_NATIVE_TLS ?= true

.PHONY: help
help:
	@echo "Targets:"
	@echo "  make dev              Run backend and frontend dev servers"
	@echo "  make dev-backend      Run FastAPI on $(BACKEND_HOST):$(BACKEND_PORT)"
	@echo "  make dev-frontend     Run Vite on $(FRONTEND_HOST):$(FRONTEND_PORT)"
	@echo "  make serve-backend    Run backend on 0.0.0.0:$(PORT) for container-like local checks"
	@echo "  make install          Install backend, agent, and frontend dependencies"
	@echo "  make check            Run lint, typecheck, and tests"
	@echo "  make test             Run all tests"
	@echo "  make lint             Run backend, agent, and frontend lint"
	@echo "  make typecheck        Run backend, agent, and frontend typecheck"
	@echo "  make format           Format backend and agent Python code"

.PHONY: dev
dev:
	$(MAKE) -j2 dev-backend dev-frontend

.PHONY: dev-backend
dev-backend:
	cd backend && uv run --frozen uvicorn app.main:app --host $(BACKEND_HOST) --port $(BACKEND_PORT)

.PHONY: dev-frontend
dev-frontend:
	cd frontend && npm run dev -- --host $(FRONTEND_HOST) --port $(FRONTEND_PORT)

.PHONY: serve-backend
serve-backend:
	cd backend && uv run --frozen uvicorn app.main:app --host 0.0.0.0 --port $(PORT)

.PHONY: install
install: install-backend install-agent install-frontend

.PHONY: install-backend
install-backend:
	cd backend && uv sync

.PHONY: install-agent
install-agent:
	cd agent && uv sync

.PHONY: install-frontend
install-frontend:
	cd frontend && npm install

.PHONY: check
check: lint typecheck test

.PHONY: test
test: test-backend test-agent test-frontend

.PHONY: test-backend
test-backend:
	cd backend && uv run --frozen pytest

.PHONY: test-agent
test-agent:
	cd agent && uv run --frozen pytest

.PHONY: test-frontend
test-frontend:
	cd frontend && npm test

.PHONY: lint
lint: lint-backend lint-agent lint-frontend

.PHONY: lint-backend
lint-backend:
	cd backend && uv run --frozen ruff check .

.PHONY: lint-agent
lint-agent:
	cd agent && uv run --frozen ruff check .

.PHONY: lint-frontend
lint-frontend:
	cd frontend && npm run lint

.PHONY: typecheck
typecheck: typecheck-backend typecheck-agent typecheck-frontend

.PHONY: typecheck-backend
typecheck-backend:
	cd backend && uv run --frozen mypy .

.PHONY: typecheck-agent
typecheck-agent:
	cd agent && uv run --frozen mypy .

.PHONY: typecheck-frontend
typecheck-frontend:
	cd frontend && npm run typecheck

.PHONY: format
format: format-backend format-agent

.PHONY: format-backend
format-backend:
	cd backend && uv run --frozen ruff format .

.PHONY: format-agent
format-agent:
	cd agent && uv run --frozen ruff format .

.PHONY: build-frontend
build-frontend:
	cd frontend && npm run build
