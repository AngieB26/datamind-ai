from __future__ import annotations

from typing import Any

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import Connection, Engine


class SchemaInspectionError(RuntimeError):
    """Raised when a PostgreSQL schema cannot be inspected."""


def inspect_schema(
    connection: Connection | Engine,
    schema_name: str,
) -> dict[str, Any]:
    """Return the tables, columns, keys, and relationships in a schema."""
    try:
        inspector = inspect(connection)

        if not inspector.has_schema(schema_name):
            raise SchemaInspectionError(
                "El esquema solicitado no existe."
            )

        table_names = sorted(
            inspector.get_table_names(schema=schema_name)
        )
        tables = []

        for table_name in table_names:
            columns = inspector.get_columns(
                table_name,
                schema=schema_name,
            )
            primary_key = inspector.get_pk_constraint(
                table_name,
                schema=schema_name,
            )
            foreign_keys = inspector.get_foreign_keys(
                table_name,
                schema=schema_name,
            )

            tables.append(
                {
                    "name": table_name,
                    "columns": [
                        {
                            "name": column["name"],
                            "type": str(column["type"]),
                            "nullable": column["nullable"],
                            "default": (
                                str(column["default"])
                                if column["default"] is not None
                                else None
                            ),
                        }
                        for column in columns
                    ],
                    "primary_key": (
                        primary_key.get("constrained_columns", []) or []
                    ),
                    "foreign_keys": [
                        {
                            "columns": fk.get("constrained_columns", []),
                            "referenced_schema": fk.get("referred_schema"),
                            "referenced_table": fk.get("referred_table"),
                            "referenced_columns": fk.get(
                                "referred_columns", []
                            ),
                        }
                        for fk in foreign_keys
                    ],
                }
            )

        return {
            "schema_name": schema_name,
            "table_count": len(tables),
            "tables": tables,
        }
    except SchemaInspectionError:
        raise
    except SQLAlchemyError as error:
        raise SchemaInspectionError(
            "No se pudo obtener la estructura del dataset."
        ) from error
