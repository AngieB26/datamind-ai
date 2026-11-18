from __future__ import annotations

import json
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import Dataset
from .dataset_engine import DatasetConnectionError, get_dataset_engine
from .dataset_sql_validator import DatasetSQLValidationError, validate_dataset_sql
from .schema_inspector import SchemaInspectionError, inspect_schema


MAX_ROWS = 100
QUERY_TIMEOUT_MS = 30_000


class DatasetQueryExecutionError(RuntimeError):
    """Error producido al ejecutar una consulta sobre un dataset."""


def execute_dataset_query(
    db: Session,
    dataset_id: int,
    query: str,
) -> dict[str, Any]:
    """Validate and execute a read-only query against one dataset."""
    try:
        dataset = db.get(Dataset, dataset_id)
        if dataset is None:
            raise DatasetQueryExecutionError(
                "No se encontró el dataset solicitado."
            )
        if dataset.status != "ready":
            raise DatasetQueryExecutionError(
                "El dataset no está disponible para consultas."
            )

        dataset_engine = get_dataset_engine(dataset.dataset_id, dataset.schema_name)
        schema_info = inspect_schema(
            dataset_engine,
            dataset.schema_name,
        )
        validated_sql = validate_dataset_sql(query, schema_info)
        limited_sql = f"""
            SELECT *
            FROM ({validated_sql}) AS datamind_result
            LIMIT {MAX_ROWS + 1}
        """

        with dataset_engine.connect() as connection:
            with connection.begin():
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                connection.exec_driver_sql(
                    f"SET LOCAL statement_timeout = '{QUERY_TIMEOUT_MS}ms'"
                )
                result = connection.exec_driver_sql(limited_sql)
                columns = list(result.keys())
                records = result.fetchall()

        has_more = len(records) > MAX_ROWS
        rows = [list(row) for row in records[:MAX_ROWS]]

        return {
            "success": True,
            "dataset_id": dataset.dataset_id,
            "dataset_name": dataset.name,
            "schema_name": dataset.schema_name,
            "sql": validated_sql,
            "columns": columns,
            "rows": jsonable_encoder(rows),
            "row_count": len(rows),
            "max_rows": MAX_ROWS,
            "truncated": has_more,
        }
    except (
        DatasetConnectionError,
        SchemaInspectionError,
        DatasetSQLValidationError,
        DatasetQueryExecutionError,
    ):
        raise
    except SQLAlchemyError as error:
        raise DatasetQueryExecutionError(
            "PostgreSQL rechazó la consulta o se superó el tiempo permitido."
        ) from error
