import sqlglot
from sqlglot.errors import ParseError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..database import engine
from sqlglot import exp

ALLOWED_TABLES = {
    "customers",
    "products",
    "orders",
    "order_details",
    "payments"
}

FORBIDDEN_FUNCTIONS = {
    "pg_sleep",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "lo_import",
    "lo_export",
    "set_config",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "dblink",
    "dblink_exec",
    "nextval",
    "setval"
}

class SQLValidationError(Exception):
    """Error producido cuando una consulta SQL no es segura."""


class QueryExecutionError(Exception):
    """Error producido al ejecutar una consulta SQL validada."""


# Consultas y operaciones que no están permitidas.
FORBIDDEN_NODES = {
    "insert",
    "update",
    "delete",
    "create",
    "drop",
    "alter",
    "command",
    "copy",
    "merge",
    "truncatetable",
    "grant",
    "revoke",
    "commit",
    "rollback",
    "transaction",
    "call",
    "execute",
    "set",
    "vacuum",
    "analyze"
}


def validate_readonly_sql(query: str) -> str:

    if not query or not query.strip():
        raise SQLValidationError("La consulta SQL está vacía.")

    if len(query) > 10000:
        raise SQLValidationError(
            "La consulta supera el tamaño permitido."
        )

    try:
        # Analizar utilizando el dialecto PostgreSQL.
        statements = sqlglot.parse(
            query,
            read="postgres"
        )

    except ParseError as error:
        raise SQLValidationError(
            "La consulta contiene errores de sintaxis SQL."
        ) from error

    # Evitar consultas múltiples.
    statements = [
        statement
        for statement in statements
        if statement is not None
    ]

    if len(statements) != 1:
        raise SQLValidationError(
            "Solo se permite una consulta SQL."
        )

    expression = statements[0]

    # Permitir únicamente consultas SELECT y operaciones
    # de combinación de resultados.
    allowed_roots = {
        "select",
        "union",
        "intersect",
        "except"
    }

    root_type = type(expression).__name__.lower()

    if root_type not in allowed_roots:
        raise SQLValidationError(
            "Solo se permiten consultas SELECT."
        )

    # Inspeccionar todos los nodos, incluidos los CTE
    # y las subconsultas.
    for node in expression.walk():

        node_type = type(node).__name__.lower()

        if node_type in FORBIDDEN_NODES:
            raise SQLValidationError(
                f"Operación SQL no permitida: {node_type}."
            )

        # Evitar SELECT INTO y SELECT FOR UPDATE.
        if node_type == "select":

            if node.args.get("into") is not None:
                raise SQLValidationError(
                    "No se permite SELECT INTO."
                )

            if node.args.get("locks"):
                raise SQLValidationError(
                    "No se permiten bloqueos FOR UPDATE."
                )

        # Identificar los nombres de los CTE permitidos.
    cte_names = {
        cte.alias_or_name.lower()
        for cte in expression.find_all(exp.CTE)
    }

    # Verificar las tablas utilizadas.
    for table in expression.find_all(exp.Table):

        table_name = table.name.lower()

        if table_name in cte_names:
            continue

        if table_name not in ALLOWED_TABLES:
            raise SQLValidationError(
                f"Tabla no autorizada: {table_name}"
            )

        if table.catalog or (
            table.db and table.db.lower() != "public"
        ):
            raise SQLValidationError(
                "Solo se permite consultar el esquema public."
            )

    # Bloquear funciones PostgreSQL peligrosas.
    for node in expression.walk():

        if isinstance(node, exp.Anonymous):
            function_name = node.name.lower()

            if function_name in FORBIDDEN_FUNCTIONS:
                raise SQLValidationError(
                    f"Función no permitida: {function_name}"
                )

    # Devolver la consulta normalizada.
    return expression.sql(dialect="postgres")


def execute_readonly_query(query: str) -> dict:
    """Valida y ejecuta una consulta de solo lectura."""

    validated_sql = validate_readonly_sql(query)

    try:
        with engine.connect() as connection:
            result = connection.execute(text(validated_sql))
            rows = [dict(row._mapping) for row in result]

        return {
            "valid": True,
            "message": "Consulta ejecutada correctamente.",
            "sql": validated_sql,
            "columns": list(result.keys()),
            "rows": rows,
            "row_count": len(rows),
        }

    except SQLAlchemyError as error:
        raise QueryExecutionError(
            "No se pudo ejecutar la consulta en PostgreSQL."
        ) from error
