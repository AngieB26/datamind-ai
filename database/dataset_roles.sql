-- ============================================
-- DATAMIND AI
-- DATASET DATABASE ROLES
-- ============================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'datamind_reader'
    ) THEN
        CREATE ROLE datamind_reader LOGIN;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'datamind_importer'
    ) THEN
        CREATE ROLE datamind_importer LOGIN;
    END IF;
END
$$;

ALTER ROLE datamind_reader
    WITH LOGIN NOSUPERUSER NOCREATEDB
    NOCREATEROLE NOREPLICATION NOBYPASSRLS;

ALTER ROLE datamind_importer
    WITH LOGIN NOSUPERUSER NOCREATEDB
    NOCREATEROLE NOREPLICATION NOBYPASSRLS;

GRANT CONNECT ON DATABASE datamind_db
TO datamind_reader, datamind_importer;

GRANT CREATE ON DATABASE datamind_db
TO datamind_importer;

REVOKE CREATE ON DATABASE datamind_db
FROM datamind_reader;

GRANT USAGE ON SCHEMA public
TO datamind_reader;

REVOKE CREATE ON SCHEMA public
FROM datamind_reader;

GRANT SELECT ON TABLE
    public.customers,
    public.products,
    public.orders,
    public.order_details,
    public.payments
TO datamind_reader;
