from __future__ import annotations

import re
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


FORBIDDEN_FUNCTIONS = {
    "current_setting",
    "dblink",
    "dblink_exec",
    "lo_export",
    "lo_import",
    "pg_cancel_backend",
    "pg_terminate_backend",
    "set_config",
}


class DatasetSQLValidationError(ValueError):
    """Error producido cuando una consulta excede el esquema autorizado."""


def _table_map(schema_info: dict[str, Any]) -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {}
    for table in schema_info.get("tables", []):
        name = table["name"].lower()
        tables[name] = {
            column["name"].lower()
            for column in table.get("columns", [])
        }
    return tables


def validate_dataset_sql(
    query: str,
    schema_info: dict[str, Any],
) -> str:
    """Validate a read-only SQL query against inspected dataset metadata."""
    if not query or not query.strip():
        raise DatasetSQLValidationError("La consulta SQL está vacía.")
    if len(query) > 10_000:
        raise DatasetSQLValidationError("La consulta supera el tamaño permitido.")

    try:
        statements = [
            item for item in sqlglot.parse(query, read="postgres")
            if item is not None
        ]
    except ParseError as error:
        raise DatasetSQLValidationError(
            "La consulta contiene errores de sintaxis SQL."
        ) from error

    if len(statements) != 1:
        raise DatasetSQLValidationError("Solo se permite una consulta SQL.")

    expression = statements[0]
    if not isinstance(expression, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise DatasetSQLValidationError("Solo se permiten consultas SELECT.")

    tables = _table_map(schema_info)
    if not tables:
        raise DatasetSQLValidationError("El dataset no contiene tablas autorizadas.")

    table_aliases: dict[str, str] = {}
    for table in expression.find_all(exp.Table):
        table_name = table.name.lower()
        if table_name not in tables:
            raise DatasetSQLValidationError(
                f"Tabla no autorizada: {table_name}."
            )
        if table.catalog or table.db:
            referenced_schema = (table.db or "").lower()
            expected_schema = str(schema_info.get("schema_name", "")).lower()
            if referenced_schema != expected_schema:
                raise DatasetSQLValidationError(
                    "Solo se permite consultar el esquema seleccionado."
                )
        table_aliases[table.alias_or_name.lower()] = table_name
        table_aliases[table_name] = table_name

    known_columns = set().union(*tables.values()) if tables else set()
    projection_aliases = {
        alias.alias.lower()
        for alias in expression.find_all(exp.Alias)
        if alias.alias
    }
    cte_names = {
        cte.alias_or_name.lower()
        for cte in expression.find_all(exp.CTE)
    }
    derived_aliases = {
        subquery.alias_or_name.lower()
        for subquery in expression.find_all(exp.Subquery)
        if subquery.alias_or_name
    }

    for column in expression.find_all(exp.Column):
        if column.is_star:
            continue
        column_name = column.name.lower()
        qualifier = (column.table or "").lower()
        if qualifier:
            if qualifier in cte_names or qualifier in derived_aliases:
                if (
                    column_name not in known_columns
                    and column_name not in projection_aliases
                ):
                    raise DatasetSQLValidationError(
                        f"Columna no reconocida: {column_name}."
                    )
                continue
            if qualifier not in table_aliases:
                raise DatasetSQLValidationError(
                    f"Alias o tabla no autorizada: {qualifier}."
                )
            table_name = table_aliases[qualifier]
            if column_name not in tables[table_name] and column_name != "*":
                raise DatasetSQLValidationError(
                    f"Columna no permitida en {table_name}: {column_name}."
                )
        elif column_name not in known_columns and column_name not in projection_aliases:
            raise DatasetSQLValidationError(
                f"Columna no reconocida: {column_name}."
            )

    for node in expression.find_all(exp.Func):
        if isinstance(node, exp.Anonymous):
            function_name = node.name.lower()
        else:
            function_name = node.sql_name().lower()
        if (
            function_name in FORBIDDEN_FUNCTIONS
            or function_name.startswith("pg_")
            or function_name.startswith("lo_")
            or function_name.startswith("dblink")
        ):
            raise DatasetSQLValidationError(
                f"Función no permitida: {function_name}."
            )

    return expression.sql(dialect="postgres")
