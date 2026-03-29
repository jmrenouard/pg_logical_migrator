# pg_logical_migrator Makefile

.PHONY: help venv install test-unit test-integration test-e2e test-all env-up env-down clean run-auto

VENV     := venv
PYTHON   := $(VENV)/bin/python
PIP      := $(VENV)/bin/pip
PYTEST   := $(VENV)/bin/pytest
TIMESTAMP := $(shell date +%Y%m%d_%H%M%S)

help:
	@echo "Available targets:"
	@echo "  install          Create .venv and install dependencies"
	@echo "  test-unit        Run unit tests"
	@echo "  test-integration Run integration tests (requires docker env)"
	@echo "  test-e2e         Run full end-to-end migration test (requires docker env)"
	@echo "  test-all         Run all tests"
	@echo "  test-report      Run tests and generate reports"
	@echo "  env-up           Start the Docker test environment"
	@echo "  env-down         Stop the Docker test environment"
	@echo "  run-auto         Run a full automated migration"
	@echo "  clean            Cleanup temporary files and logs"

venv:
	@test -d $(VENV) || python3 -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

env-up:
	cd test_env && docker compose down -v --remove-orphans 2>/dev/null || true
	cd test_env && docker compose up -d
	@echo "Waiting for databases to be ready..."
	sleep 10
	./test_env/setup_pagila.sh

env-down:
	cd test_env && docker compose down -v --remove-orphans

test-unit:
	PYTHONPATH=. $(PYTEST) tests/unit

test-integration:
	PYTHONPATH=. $(PYTEST) tests/integration

test-e2e:
	PYTHONPATH=. $(PYTEST) tests/e2e

test-all: test-unit test-integration test-e2e

test-report: install
	@mkdir -p RESULTS/$(TIMESTAMP)
	PYTHONPATH=. $(PYTEST) tests/unit --html=RESULTS/$(TIMESTAMP)/unit_tests.html --self-contained-html
	PYTHONPATH=. $(PYTHON) src/main.py --auto --results-dir RESULTS/$(TIMESTAMP)
	@echo "Reports generated in RESULTS/$(TIMESTAMP)/"

run-auto:
	PYTHONPATH=. $(PYTHON) src/main.py --auto

clean:
	rm -rf RESULTS/*
	rm -f pg_migrator.log
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name "$(VENV)" -exec rm -rf {} + 2>/dev/null || true
