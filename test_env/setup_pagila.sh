#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
CONTAINER_SOURCE="pg_source"
CONTAINER_TARGET="pg_target"
DB_NAME="test_migration"

HOST_SOURCE=${PGHOST_SOURCE:-127.0.0.1}
HOST_TARGET=${PGHOST_TARGET:-127.0.0.1}


echo "Waiting for PostgreSQL servers to be healthy..."
for HOST in "${HOST_SOURCE}" "${HOST_TARGET}"; do
    until PGPASSWORD=secret pg_isready -h "${HOST}" -U postgres; do
        sleep 2;
        echo -n "."
    done
    echo " ${HOST} is ready."
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
for DB in ${DB_NAME} ${DB_NAME}_2 ${DB_NAME}_3; do
    PGPASSWORD=secret psql -U postgres -h ${HOST_SOURCE} -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DB}' AND pid <> pg_backend_pid();" postgres
    PGPASSWORD=secret psql -U postgres -h ${HOST_SOURCE} -c "SELECT pg_terminate_backend(active_pid) FROM pg_replication_slots WHERE database = '${DB}' AND active_pid IS NOT NULL;" postgres || true
    PGPASSWORD=secret psql -U postgres -h ${HOST_SOURCE} -c "SELECT pg_drop_replication_slot(slot_name) FROM pg_replication_slots WHERE database = '${DB}';" postgres || true
    PGPASSWORD=secret psql -U postgres -h ${HOST_SOURCE} -c "DROP DATABASE IF EXISTS ${DB};" postgres
    PGPASSWORD=secret psql -U postgres -h ${HOST_SOURCE} -c "CREATE DATABASE ${DB};" postgres
done

for DB in ${DB_NAME} ${DB_NAME}_2 ${DB_NAME}_3; do
    echo "Loading schema into source for ${DB}..."
    PGPASSWORD=secret psql -U postgres -d ${DB} -h ${HOST_SOURCE} < "${DIR}/pagila-schema.sql"

    echo "Loading data into source for ${DB}..."
    PGPASSWORD=secret psql -U postgres -d ${DB} -h ${HOST_SOURCE} < "${DIR}/pagila-data.sql"

    echo "Injecting no_pk_table for testing into ${DB}..."
    PGPASSWORD=secret psql -U postgres -d ${DB} -h ${HOST_SOURCE} -c "
    CREATE TABLE public.no_pk_table (
        id integer,
        random_data text
    );
    INSERT INTO public.no_pk_table (id, random_data)
    SELECT generate_series(1, 10), md5(random()::text);
    "

    echo "Injecting extra test data (multi-schema, no-PK, unlogged, LOBs) into ${DB}..."
    PGPASSWORD=secret psql -U postgres -d ${DB} -h ${HOST_SOURCE} < "${DIR}/extra_test_data.sql"
done

echo "Injecting VERY LARGE DATASET (100 million rows in schema_large) only to ${DB_NAME}..."
echo "  -> This step is slow by design. Please wait..."
PGPASSWORD=secret psql -U postgres -d ${DB_NAME} -h ${HOST_SOURCE} < "${DIR}/large_data.sql"

echo "Setup complete!"
