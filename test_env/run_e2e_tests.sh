#!/bin/bash
set -e

echo "Running E2E tests inside container..."

# 1. Initialize databases with pagila dataset
./test_env/setup_pagila.sh

# 2. Generate a custom configuration for the tests
cat <<EOF > tests/test_config.ini
[source]
host = pg_source
port = 5432
user = postgres
password = secret
database = test_migration

[destination]
host = pg_target
port = 5432
user = postgres
password = secret
database = test_migration

[replication]
publication_name = pub_test_migration
subscription_name = sub_test_migration
sync_lobs = true
sync_unlogged = true
drop_destination = true
target_schema = all
EOF

# Ensure we use the proper python environment and config
export PYTHONPATH=.
export MIGRATOR_CONFIG=tests/test_config.ini

# 3. Run the complete test suite
TEST_TARGETS=${@:-tests/e2e/}

echo "Running pytest suite on: ${TEST_TARGETS}"
pytest -vv ${TEST_TARGETS} \
    --cov=src \
    --cov-report=term \
    --cov-report=html:RESULTS/coverage

# Fix permissions of the results directory to match the host user
chown -R $(stat -c '%u:%g' /app) /app/RESULTS || true
