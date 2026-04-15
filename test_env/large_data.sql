-- large_data.sql
-- Scenario: Very large table to slow down migration

CREATE SCHEMA IF NOT EXISTS schema_large;

CREATE TABLE schema_large.heavy_table (
    id serial primary key,
    payload text,
    ts timestamp default now()
);

-- Note: 100M rows will take significant time to generate and space to store.
-- You can adjust the 100000000 value below if needed.
INSERT INTO schema_large.heavy_table (payload)
SELECT 'payload_data_chunk_' || (s.i % 1000)
FROM generate_series(1, 1000000) s(i);
