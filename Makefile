.PHONY: help up down migrate logs shell test lint eval clean traces

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Start all services in detached mode
	docker-compose up -d

down: ## Stop and remove all containers
	docker-compose down

logs: ## Follow logs from all services
	docker-compose logs -f

logs-backend: ## Follow backend logs only
	docker-compose logs -f backend

logs-celery: ## Follow celery worker logs only
	docker-compose logs -f celery-worker

shell: ## Open shell in backend container
	docker-compose exec backend /bin/bash

shell-db: ## Open psql shell in database
	docker-compose exec postgres psql -U raguser -d ragdb

migrate: ## Run database migrations
	docker-compose exec backend alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create MSG="add new column")
	docker-compose exec backend alembic revision --autogenerate -m "$(MSG)"

test: ## Run backend tests
	docker-compose exec backend pytest

test-cov: ## Run tests with coverage
	docker-compose exec backend pytest --cov=app --cov-report=html

lint: ## Run linters (ruff, black)
	docker-compose exec backend ruff check app
	docker-compose exec backend black --check app

format: ## Format code with black
	docker-compose exec backend black app
	docker-compose exec backend ruff check --fix app

eval: ## Run evaluation pipeline
	docker-compose exec backend python -m app.evals.runner

traces: ## Open Jaeger UI for viewing distributed traces
	@echo "Opening Jaeger UI at http://localhost:16686"
	@open http://localhost:16686 || xdg-open http://localhost:16686

clean: ## Remove all containers, volumes, and build artifacts
	docker-compose down -v
	rm -rf backend/__pycache__ backend/app/__pycache__ backend/.pytest_cache
	rm -rf frontend/.next frontend/node_modules

dev-backend: ## Run backend locally (not in docker)
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend: ## Run frontend locally
	cd frontend && npm run dev

celery-worker: ## Run celery worker locally
	cd backend && celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2

redis-cli: ## Open redis-cli
	docker-compose exec redis redis-cli
