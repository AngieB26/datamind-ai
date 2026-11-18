-- Ejecutar como postgres SOLO DESPUÉS de provisionar y probar todos los roles
-- individuales. Mantiene intactos los permisos sobre el esquema public.
BEGIN;

DO $block$
DECLARE
    schema_record RECORD;
BEGIN
    FOR schema_record IN
        SELECT n.nspname
        FROM pg_catalog.pg_namespace AS n
        WHERE n.nspname ~ '^dataset_[a-f0-9]{12,32}$'
    LOOP
        EXECUTE pg_catalog.format(
            'REVOKE ALL PRIVILEGES ON SCHEMA %I FROM datamind_reader',
            schema_record.nspname
        );
        EXECUTE pg_catalog.format(
            'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA %I FROM datamind_reader',
            schema_record.nspname
        );
        EXECUTE pg_catalog.format(
            'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA %I FROM datamind_reader',
            schema_record.nspname
        );
        EXECUTE pg_catalog.format(
            'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I REVOKE SELECT ON TABLES FROM %I',
            'datamind_importer',
            schema_record.nspname,
            'datamind_reader'
        );
    END LOOP;
END
$block$;

COMMIT;
