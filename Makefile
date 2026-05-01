# pg_logical_migrator Makefile

.PHONY: help venv install build build-clean test-unit test-integration test-e2e test-packaging test-all env-up env-down clean run-pipeline

VENV          := venv
PYTHON        := $(VENV)/bin/python
PIP           := $(VENV)/bin/pip
PYTEST        := $(VENV)/bin/pytest
PYINSTALLER   := $(VENV)/bin/pyinstaller
BIN_NAME      := pg_migrator
TIMESTAMP     := $(shell date +%Y%m%d_%H%M%S)

help:
	@echo "Available targets:"
	@echo "  install          Create .venv and install dependencies"
	@echo "  build            Bundle the tool into a single executable (dist/$(BIN_NAME))"
	@echo "  build-clean      Remove PyInstaller build artefacts (build/ dist/ *.spec)"
	@echo "  test-unit        Run unit tests"
	@echo "  test-integration Run integration tests (requires docker env)"
	@echo "  test-e2e         Run full end-to-end migration test (requires docker env)"
	@echo "  test-packaging   Run packaging end-to-end test (build and validate binaries/packages)"
	@echo "  test-all         Run all tests (unit, integration, e2e, packaging)"
	@echo "  test-report      Run tests and generate reports"
	@echo "  env-up           Start the Docker test environment"
	@echo "  env-down         Stop the Docker test environment"
	@echo "  run-pipeline     Run a full piplelined migration via init-replication and post-migration"
	@echo "  clean            Cleanup temporary files, logs and build artefacts"

venv:
	@test -d $(VENV) || python3 -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install pyinstaller

build: install
	@echo ">>> Bundling $(BIN_NAME) into a single executable..."
	$(PYINSTALLER) \
		--onefile \
		--name $(BIN_NAME) \
		--add-data "src:src" \
		--add-data "config_migrator.sample.ini:."	\
		pg_migrator.py
	@echo ">>> Executable ready: dist/$(BIN_NAME)"

build-clean:
	rm -rf build dist $(BIN_NAME).spec

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

test-all: test-unit test-integration test-e2e test-packaging

test-packaging:
	./e2e_packaging_test.sh

test-report: install
	@mkdir -p RESULTS/$(TIMESTAMP)
	PYTHONPATH=. $(PYTEST) tests/unit --html=RESULTS/$(TIMESTAMP)/unit_tests.html --self-contained-html
	PYTHONPATH=. $(PYTHON) pg_migrator.py init-replication --drop-dest --results-dir RESULTS/$(TIMESTAMP)
	PYTHONPATH=. $(PYTHON) pg_migrator.py post-migration --results-dir RESULTS/$(TIMESTAMP)
	@echo "Reports generated in RESULTS/$(TIMESTAMP)/"

run-pipeline:
	PYTHONPATH=. $(PYTHON) pg_migrator.py init-replication --drop-dest
	PYTHONPATH=. $(PYTHON) pg_migrator.py post-migration

clean: build-clean
	rm -rf RESULTS/*
	rm -f pg_migrator.log
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name "$(VENV)" -exec rm -rf {} + 2>/dev/null || true
