-- extra_test_data.sql
-- Extra test scenarios for pg_logical_migrator

-- 1. Schema with tables without primary keys
CREATE SCHEMA IF NOT EXISTS schema_no_pk;

CREATE TABLE schema_no_pk.table_no_pk (
    id integer,
    name text,
    created_at timestamp default now()
);

INSERT INTO schema_no_pk.table_no_pk (id, name) 
SELECT i, 'no_pk_' || i FROM generate_series(1, 100) s(i);


-- 2. Schema with unlogged tables
CREATE SCHEMA IF NOT EXISTS schema_unlogged;

CREATE UNLOGGED TABLE schema_unlogged.unlogged_test (
    id serial primary key,
    temp_data text
);

INSERT INTO schema_unlogged.unlogged_test (temp_data)
SELECT 'temp_' || i FROM generate_series(1, 50) s(i);


-- 3. Schema with table containing LOBs (Large Objects)
CREATE SCHEMA IF NOT EXISTS schema_lobs;

CREATE TABLE schema_lobs.table_with_lobs (
    id serial primary key,
    description text,
    picture_oid oid
);

-- Ingest a small Large Object
DO $$
DECLARE
    loid oid;
BEGIN
    loid := lo_create(0);
    INSERT INTO schema_lobs.table_with_lobs (description, picture_oid) 
    VALUES ('Test LOB object', loid);
    -- Write some dummy data to the LO
    PERFORM lowrite(lo_open(loid, 131072), '\xdeadbeef'::bytea);
END $$;
