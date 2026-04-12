#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
CONTAINER_SOURCE="pg_source"
CONTAINER_TARGET="pg_target"
DB_NAME="test_migration"

echo "Waiting for PostgreSQL containers to be healthy..."
for CONTAINER in "${CONTAINER_SOURCE}" "${CONTAINER_TARGET}"; do
    until [ "$(docker inspect -f '{{.State.Health.Status}}' "${CONTAINER}")" = "healthy" ]; do
        sleep 2;
        echo -n "."
    done
    echo " ${CONTAINER} is ready."
done

# Download Pagila if not exists
if [ ! -f "${DIR}/pagila-schema.sql" ]; then
    echo "Downloading Pagila schema..."
    curl -sL https://raw.githubusercontent.com/devrimgunduz/pagila/master/pagila-schema.sql -o "${DIR}/pagila-schema.sql"
fi

if [ ! -f "${DIR}/pagila-data.sql" ]; then
    echo "Downloading Pagila data..."
    curl -sL https://raw.githubusercontent.com/devrimgunduz/pagila/master/pagila-data.sql -o "${DIR}/pagila-data.sql"
fi

echo "Resetting source database (drop & recreate)..."
docker exec -i ${CONTAINER_SOURCE} psql -U postgres -h localhost -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DB_NAME}' AND pid <> pg_backend_pid();" postgres
docker exec -i ${CONTAINER_SOURCE} psql -U postgres -h localhost -c "DROP DATABASE IF EXISTS ${DB_NAME};" postgres
docker exec -i ${CONTAINER_SOURCE} psql -U postgres -h localhost -c "CREATE DATABASE ${DB_NAME};" postgres

echo "Loading schema into source..."
docker exec -i ${CONTAINER_SOURCE} psql -U postgres -d ${DB_NAME} -h localhost < "${DIR}/pagila-schema.sql"

echo "Loading data into source..."
docker exec -i ${CONTAINER_SOURCE} psql -U postgres -d ${DB_NAME} -h localhost < "${DIR}/pagila-data.sql"

echo "Injecting no_pk_table for testing..."
docker exec -i ${CONTAINER_SOURCE} psql -U postgres -d ${DB_NAME} -h localhost -c "
CREATE TABLE public.no_pk_table (
    id integer,
    random_data text
);
INSERT INTO public.no_pk_table (id, random_data)
SELECT generate_series(1, 10), md5(random()::text);
"

echo "Injecting extra test data (multi-schema, no-PK, unlogged, LOBs)..."
docker exec -i ${CONTAINER_SOURCE} psql -U postgres -d ${DB_NAME} -h localhost < "${DIR}/extra_test_data.sql"

echo "Injecting VERY LARGE DATASET (100 million rows in schema_large)..."
echo "  -> This step is slow by design. Please wait..."
docker exec -i ${CONTAINER_SOURCE} psql -U postgres -d ${DB_NAME} -h localhost < "${DIR}/large_data.sql"

echo "Setup complete!"
