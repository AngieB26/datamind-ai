
-- =========================================================
-- DATAMIND AI
-- LECTURA AISLADA POR DATASET
-- PostgreSQL 18
-- Ejecutar exclusivamente como administrador postgres
-- =========================================================

BEGIN;

DO $$
BEGIN
    IF current_user <> 'postgres' THEN
        RAISE EXCEPTION
            'Este script debe ejecutarse como postgres.';
    END IF;
END
$$;

-- Esquema administrativo privado.
CREATE SCHEMA IF NOT EXISTS datamind_security
    AUTHORIZATION postgres;

ALTER SCHEMA datamind_security OWNER TO postgres;

REVOKE ALL ON SCHEMA datamind_security FROM PUBLIC;

GRANT USAGE ON SCHEMA datamind_security
TO datamind_importer;


-- =========================================================
-- 1. CREAR O ACTUALIZAR UN ROL DE LECTURA POR DATASET
-- =========================================================

CREATE OR REPLACE FUNCTION
datamind_security.provision_dataset_reader(
    p_dataset_id BIGINT,
    p_schema_name TEXT,
    p_password TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$

DECLARE
    v_role_name TEXT;
    v_schema_owner NAME;
    v_role_oid OID;
    v_table_count INTEGER;
    v_dataset_schema TEXT;

BEGIN
    IF p_dataset_id IS NULL OR p_dataset_id <= 0 THEN
        RAISE EXCEPTION 'ID de dataset inválido.';
    END IF;

    v_role_name := 'dm_reader_ds_' || p_dataset_id::TEXT;

    -- Verificar que el dataset exista y tenga un propietario válido.
    SELECT d.schema_name
    INTO v_dataset_schema
    FROM public.datasets AS d
    WHERE d.dataset_id = p_dataset_id
      AND d.is_builtin = FALSE
      AND (
          d.owner_id IS NOT NULL
          OR d.guest_session_id IS NOT NULL
      );

    IF v_dataset_schema IS DISTINCT FROM p_schema_name THEN
        RAISE EXCEPTION
            'El esquema no corresponde a un dataset autorizado.';
    END IF;

    IF p_schema_name !~ '^dataset_[a-f0-9]{12,32}$' THEN
        RAISE EXCEPTION 'Nombre de esquema inválido.';
    END IF;

    IF p_password IS NULL
       OR p_password !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'Credencial de lectura inválida.';
    END IF;

    -- El esquema debe pertenecer al importador.
    SELECT pg_catalog.pg_get_userbyid(nspowner)
    INTO v_schema_owner
    FROM pg_catalog.pg_namespace
    WHERE nspname = p_schema_name;

    IF v_schema_owner IS DISTINCT FROM 'datamind_importer' THEN
        RAISE EXCEPTION
            'El esquema no existe o no pertenece al importador.';
    END IF;

    SELECT COUNT(*)
    INTO v_table_count
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n
        ON n.oid = c.relnamespace
    WHERE n.nspname = p_schema_name
      AND c.relkind IN ('r', 'p');

    IF v_table_count = 0 THEN
        RAISE EXCEPTION 'El dataset no contiene tablas.';
    END IF;

    -- Comprobar si el rol ya existe.
    SELECT oid
    INTO v_role_oid
    FROM pg_catalog.pg_roles
    WHERE rolname = v_role_name;

    IF v_role_oid IS NOT NULL THEN

        -- No aceptar roles con membresías externas.
        IF EXISTS (
            SELECT 1
            FROM pg_catalog.pg_auth_members
            WHERE member = v_role_oid
               OR roleid = v_role_oid
        ) THEN
            RAISE EXCEPTION
                'El rol tiene membresías inesperadas.';
        END IF;

        -- No modificar roles propietarios de objetos.
        IF EXISTS (
            SELECT 1
            FROM pg_catalog.pg_shdepend
            WHERE refobjid = v_role_oid
              AND refclassid =
                  pg_catalog.to_regclass('pg_catalog.pg_authid')
              AND deptype = 'o'
        ) THEN
            RAISE EXCEPTION
                'El rol tiene objetos propios.';
        END IF;

        EXECUTE pg_catalog.format(
            'ALTER ROLE %I WITH LOGIN NOINHERIT
             NOSUPERUSER NOCREATEDB NOCREATEROLE
             NOREPLICATION NOBYPASSRLS PASSWORD %L',
            v_role_name,
            p_password
        );

    ELSE

        EXECUTE pg_catalog.format(
            'CREATE ROLE %I WITH LOGIN NOINHERIT
             NOSUPERUSER NOCREATEDB NOCREATEROLE
             NOREPLICATION NOBYPASSRLS PASSWORD %L',
            v_role_name,
            p_password
        );

    END IF;

    -- Acceso exclusivo a la base de datos.
    EXECUTE pg_catalog.format(
        'GRANT CONNECT ON DATABASE %I TO %I',
        pg_catalog.current_database(),
        v_role_name
    );

    -- Acceso únicamente al esquema de este dataset.
    EXECUTE pg_catalog.format(
        'GRANT USAGE ON SCHEMA %I TO %I',
        p_schema_name,
        v_role_name
    );

    -- Lectura de sus tablas actuales.
    EXECUTE pg_catalog.format(
        'GRANT SELECT ON ALL TABLES IN SCHEMA %I TO %I',
        p_schema_name,
        v_role_name
    );

    -- Lectura de tablas futuras creadas por el importador.
    EXECUTE pg_catalog.format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I
         IN SCHEMA %I GRANT SELECT ON TABLES TO %I',
        'datamind_importer',
        p_schema_name,
        v_role_name
    );

    RETURN v_role_name;

END;
$function$;


-- =========================================================
-- 2. ELIMINAR EL ROL ASOCIADO A UN DATASET
-- =========================================================

CREATE OR REPLACE FUNCTION
datamind_security.drop_dataset_reader(
    p_dataset_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$

DECLARE
    v_role_name TEXT;
    v_role_oid OID;
    v_dataset_schema TEXT;

BEGIN
    IF p_dataset_id IS NULL OR p_dataset_id <= 0 THEN
        RAISE EXCEPTION 'ID de dataset inválido.';
    END IF;

    v_role_name := 'dm_reader_ds_' || p_dataset_id::TEXT;

    -- No permitir eliminar roles de datasets inexistentes
    -- o que no tengan un propietario o sesión identificada.
    SELECT d.schema_name
    INTO v_dataset_schema
    FROM public.datasets AS d
    WHERE d.dataset_id = p_dataset_id
      AND d.is_builtin = FALSE
      AND (
          d.owner_id IS NOT NULL
          OR d.guest_session_id IS NOT NULL
      );

    IF v_dataset_schema IS NULL THEN
        RAISE EXCEPTION
            'No existe un dataset autorizado para este rol.';
    END IF;

    SELECT oid
    INTO v_role_oid
    FROM pg_catalog.pg_roles
    WHERE rolname = v_role_name;

    IF v_role_oid IS NULL THEN
        RETURN FALSE;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_auth_members
        WHERE member = v_role_oid
           OR roleid = v_role_oid
    ) THEN
        RAISE EXCEPTION 'El rol tiene membresías inesperadas.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_shdepend
        WHERE refobjid = v_role_oid
          AND refclassid =
              pg_catalog.to_regclass('pg_catalog.pg_authid')
          AND deptype = 'o'
    ) THEN
        RAISE EXCEPTION 'El rol posee objetos.';
    END IF;

    -- Revocar sus permisos y privilegios predeterminados.
    EXECUTE pg_catalog.format(
        'DROP OWNED BY %I',
        v_role_name
    );

    EXECUTE pg_catalog.format(
        'DROP ROLE %I',
        v_role_name
    );

    RETURN TRUE;

END;
$function$;


-- =========================================================
-- 3. RESTRINGIR LA EJECUCIÓN DE LAS FUNCIONES
-- =========================================================

REVOKE ALL ON FUNCTION
datamind_security.provision_dataset_reader(
    BIGINT, TEXT, TEXT
)
FROM PUBLIC;

REVOKE ALL ON FUNCTION
datamind_security.drop_dataset_reader(BIGINT)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
datamind_security.provision_dataset_reader(
    BIGINT, TEXT, TEXT
)
TO datamind_importer;

GRANT EXECUTE ON FUNCTION
datamind_security.drop_dataset_reader(BIGINT)
TO datamind_importer;

COMMIT;
