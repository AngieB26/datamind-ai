from sqlalchemy.exc import SQLAlchemyError
from fastapi.encoders import jsonable_encoder

from ..database import engine
from .sql_validator import validate_readonly_sql


MAX_ROWS = 100
QUERY_TIMEOUT = "5000ms"


class QueryExecutionError(Exception):
    """Error al ejecutar una consulta SQL."""


def execute_readonly_query(query: str):

    # Primera barrera: validar la consulta.
    validated_sql = validate_readonly_sql(query)

    # Limitar el resultado a 101 filas para detectar
    # si existen más de las 100 permitidas.
    limited_sql = f"""
        SELECT *
        FROM ({validated_sql}) AS datamind_result
        LIMIT {MAX_ROWS + 1}
    """

    try:

        with engine.connect() as connection:

            with connection.begin():

                # Transacción de solo lectura.
                connection.exec_driver_sql(
                    "SET TRANSACTION READ ONLY"
                )

                # Tiempo máximo de ejecución.
                connection.exec_driver_sql(
                    f"SET LOCAL statement_timeout = '{QUERY_TIMEOUT}'"
                )

                result = connection.exec_driver_sql(limited_sql)

                columns = list(result.keys())

                records = [
                    list(row)
                    for row in result.fetchall()
                ]

                has_more = len(records) > MAX_ROWS

                records = records[:MAX_ROWS]

                return {
                    "success": True,
                    "columns": columns,
                    "rows": jsonable_encoder(records),
                    "row_count": len(records),
                    "max_rows": MAX_ROWS,
                    "truncated": has_more,
                    "sql": validated_sql
                }

    except SQLAlchemyError as error:

        raise QueryExecutionError(
            "PostgreSQL rechazó la consulta o se superó el tiempo permitido."
        ) from error