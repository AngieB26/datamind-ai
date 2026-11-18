from __future__ import annotations

import re
from typing import Any

import sqlglot
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from .dataset_import_engine import (
    DatasetImportConnectionError,
    get_dataset_import_engine,
)
from .dataset_credentials import (
    DatasetCredentialError,
    derive_dataset_reader_password,
)


class SQLImportError(RuntimeError):
    """Error producido durante la validación o importación de un script."""


SCHEMA_NAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
ALLOWED_ROOTS = {"create", "insert"}
FORBIDDEN_TERMS = {
    "alter",
    "copy",
    "drop",
    "grant",
    "revoke",
    "vacuum",
    "truncate",
    "execute",
    "call",
}


def validate_sql_script(sql_content: str) -> list[str]:
    """Validate an import script and return normalized SQL statements."""
    if not sql_content or not sql_content.strip():
        raise SQLImportError("El archivo SQL está vacío.")
    if len(sql_content) > 5_000_000:
        raise SQLImportError("El archivo SQL supera el tamaño permitido.")

    try:
        expressions = [
            expression
            for expression in sqlglot.parse(sql_content, read="postgres")
            if expression is not None
        ]
    except sqlglot.errors.ParseError as error:
        raise SQLImportError("El archivo SQL contiene errores de sintaxis.") from error

    if not expressions:
        raise SQLImportError("El archivo SQL no contiene instrucciones.")

    statements: list[str] = []
    for expression in expressions:
        root_type = type(expression).__name__.lower()
        normalized = expression.sql(dialect="postgres")
        lowered = normalized.lower()

        if root_type not in ALLOWED_ROOTS:
            raise SQLImportError(
                "Solo se permiten CREATE TABLE, CREATE INDEX e INSERT INTO."
            )
        if any(re.search(rf"\b{term}\b", lowered) for term in FORBIDDEN_TERMS):
            raise SQLImportError("El script contiene una instrucción no permitida.")

        # Mantener los INSERT idempotentes, pero no permitir que un archivo
        # importado modifique filas existentes mediante DO UPDATE.
        if re.search(r"\bon\s+conflict\b", lowered):
            if not re.search(r"\bdo\s+nothing\b", lowered):
                raise SQLImportError(
                    "Solo se permite ON CONFLICT DO NOTHING."
                )
            if re.search(r"\bdo\s+update\b", lowered):
                raise SQLImportError(
                    "No se permite ON CONFLICT DO UPDATE."
                )

        if root_type == "create":
            kind = str(expression.args.get("kind", "")).lower()
            if kind not in {"table", "index"}:
                raise SQLImportError(
                    "Solo se permiten CREATE TABLE y CREATE INDEX."
                )

        statements.append(normalized)

    return statements


def import_sql_script(
    sql_content: str,
    schema_name: str,
    dataset_id: int,
    db_engine: Engine | None = None,
) -> dict[str, Any]:
    'Importa SQL y provisiona un rol de lectura exclusivo para el dataset.'
    if not SCHEMA_NAME_PATTERN.fullmatch(schema_name):
        raise SQLImportError("El nombre del esquema no es válido.")
    if not isinstance(dataset_id, int) or isinstance(dataset_id, bool) or dataset_id <= 0:
        raise SQLImportError("El identificador del dataset no es válido.")

    statements = validate_sql_script(sql_content)
    try:
        reader_password = derive_dataset_reader_password(dataset_id)
    except DatasetCredentialError as error:
        raise SQLImportError(
            "Falta configurar DATASET_ROLE_SECRET o no cumple los requisitos."
        ) from error
    try:
        import_engine = (
            db_engine
            if db_engine is not None
            else get_dataset_import_engine()
        )
        with import_engine.begin() as connection:
            preparer = connection.dialect.identifier_preparer
            quoted_schema = preparer.quote_identifier(schema_name)
            connection.exec_driver_sql(f"CREATE SCHEMA {quoted_schema}")
            connection.exec_driver_sql(
                f"SET LOCAL search_path TO {quoted_schema}, pg_catalog"
            )
            connection.exec_driver_sql(
                "SET LOCAL statement_timeout = '30000ms'"
            )

            for statement in statements:
                connection.exec_driver_sql(statement)

            # Provisionar el rol exclusivo de lectura de este dataset.
            # La función SECURITY DEFINER realiza la operación administrativa.
            connection.execute(
                text(
                    "SELECT datamind_security.provision_dataset_reader("
                    " :dataset_id, :schema_name, :password)"
                ),
                {
                    "dataset_id": dataset_id,
                    "schema_name": schema_name,
                    "password": reader_password,
                },
            )

            inspector = inspect(connection)
            tables = sorted(
                inspector.get_table_names(schema=schema_name)
            )
            if not tables:
                raise SQLImportError(
                    "La importación no generó ninguna tabla."
                )

            total_rows = 0
            for table_name in tables:
                quoted_table = preparer.quote_identifier(table_name)
                result = connection.exec_driver_sql(
                    f"SELECT COUNT(*) FROM {quoted_schema}.{quoted_table}"
                )
                total_rows += result.scalar_one()

            return {
                "schema_name": schema_name,
                "table_count": len(tables),
                "row_count": total_rows,
                "tables": tables,
            }
    except SQLImportError:
        raise
    except DatasetImportConnectionError as error:
        raise SQLImportError(
            "No se pudo configurar la conexión de importación."
        ) from error
    except SQLAlchemyError as error:
        raise SQLImportError(
            "No se pudo completar la importación. "
            "La transacción fue cancelada."
        ) from error
