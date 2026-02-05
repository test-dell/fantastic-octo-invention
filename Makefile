# =============================================================================
# Makefile - 4-Digit Number Guessing Game
# =============================================================================
# Common commands for development and deployment
#
# Usage:
#   make help      - Show available commands
#   make install   - Install dependencies
#   make run       - Run development server
#   make test      - Run tests
#   make docker    - Build and run with Docker

.PHONY: help install install-dev run test lint format clean docker docker-build docker-run docker-stop docker-logs

# Default target
help:
	@echo "Available commands:"
	@echo ""
	@echo "  Development:"
	@echo "    make install      Install production dependencies"
	@echo "    make install-dev  Install development dependencies"
	@echo "    make run          Run development server"
	@echo "    make test         Run tests with coverage"
	@echo "    make lint         Run linter (flake8)"
	@echo "    make format       Format code with black"
	@echo "    make clean        Remove cache and build files"
	@echo ""
	@echo "  Docker:"
	@echo "    make docker       Build and run with Docker Compose"
	@echo "    make docker-build Build Docker image"
	@echo "    make docker-run   Run Docker container"
	@echo "    make docker-stop  Stop Docker container"
	@echo "    make docker-logs  View Docker logs"
	@echo ""
	@echo "  Production:"
	@echo "    make prod         Run production server with Gunicorn"
	@echo "    make docker-prod  Run production Docker setup"

# -----------------------------------------------------------------------------
# Development Commands
# -----------------------------------------------------------------------------

install:
	pip install -r requirements.txt

install-dev: install
	pip install -r requirements-dev.txt

run:
	DEBUG=true python app.py

test:
	pytest --cov=. --cov-report=term-missing -v

test-quick:
	pytest -v -x

lint:
	flake8 app.py config.py --max-line-length=120 --ignore=E501,W503

format:
	black --line-length=120 app.py config.py

typecheck:
	mypy app.py config.py --ignore-missing-imports

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	rm -f coverage.xml 2>/dev/null || true

# -----------------------------------------------------------------------------
# Docker Commands
# -----------------------------------------------------------------------------

docker: docker-build docker-run

docker-build:
	docker-compose build

docker-run:
	docker-compose up -d

docker-stop:
	docker-compose down

docker-logs:
	docker-compose logs -f

docker-shell:
	docker-compose exec app /bin/sh

docker-clean:
	docker-compose down -v --rmi local

# -----------------------------------------------------------------------------
# Production Commands
# -----------------------------------------------------------------------------

prod:
	gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:5000 app:app

docker-prod:
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

docker-prod-logs:
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f
