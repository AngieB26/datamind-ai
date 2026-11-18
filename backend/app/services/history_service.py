import json

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..history_database import history_engine


class HistoryPersistenceError(Exception):
    """Error al guardar o recuperar el historial."""


def save_query_history(
    dataset_id: int,
    question: str,
    generated_sql: str,
    row_count: int,
    truncated: bool,
    result_columns: list,
    result_rows: list,
    user_id: int | None = None,
) -> int:
    """Guarda una consulta vinculada a una cuenta registrada."""

    if user_id is None:
        raise HistoryPersistenceError(
            "El historial permanente requiere un usuario registrado."
        )

    try:
        with history_engine.begin() as connection:
            result = connection.execute(
                text("""
                    INSERT INTO public.query_history (
                        dataset_id,
                        user_id,
                        question,
                        generated_sql,
                        row_count,
                        truncated,
                        result_columns,
                        result_rows
                    )
                    VALUES (
                        :dataset_id,
                        :user_id,
                        :question,
                        :generated_sql,
                        :row_count,
                        :truncated,
                        CAST(:result_columns AS jsonb),
                        CAST(:result_rows AS jsonb)
                    )
                    RETURNING history_id
                """),
                {
                    "dataset_id": dataset_id,
                    "user_id": user_id,
                    "question": question,
                    "generated_sql": generated_sql,
                    "row_count": row_count,
                    "truncated": truncated,
                    "result_columns": json.dumps(
                        result_columns,
                        ensure_ascii=False,
                    ),
                    "result_rows": json.dumps(
                        result_rows,
                        ensure_ascii=False,
                    ),
                },
            )

            return result.scalar_one()

    except SQLAlchemyError as error:
        raise HistoryPersistenceError(
            "No se pudieron guardar los resultados del historial."
        ) from error


def get_recent_history(
    limit: int = 20,
    dataset_id: int | None = None,
    user_id: int | None = None,
) -> list[dict]:
    """Recupera exclusivamente el historial de una cuenta registrada."""

    if user_id is None:
        raise HistoryPersistenceError(
            "Se requiere un usuario para recuperar el historial."
        )

    try:
        with history_engine.connect() as connection:
            if dataset_id is None:
                statement = text("""
                    SELECT
                        history_id,
                        dataset_id,
                        question,
                        generated_sql,
                        row_count,
                        truncated,
                        result_columns,
                        result_rows,
                        created_at
                    FROM public.query_history
                    WHERE user_id = :user_id
                    ORDER BY created_at DESC, history_id DESC
                    LIMIT :limit
                """)
                parameters = {
                    "user_id": user_id,
                    "limit": limit,
                }
            else:
                statement = text("""
                    SELECT
                        history_id,
                        dataset_id,
                        question,
                        generated_sql,
                        row_count,
                        truncated,
                        result_columns,
                        result_rows,
                        created_at
                    FROM public.query_history
                    WHERE user_id = :user_id
                      AND dataset_id = :dataset_id
                    ORDER BY created_at DESC, history_id DESC
                    LIMIT :limit
                """)
                parameters = {
                    "user_id": user_id,
                    "dataset_id": dataset_id,
                    "limit": limit,
                }

            result = connection.execute(statement, parameters)

            return [
                dict(row)
                for row in result.mappings().all()
            ]

    except SQLAlchemyError as error:
        raise HistoryPersistenceError(
            "No se pudo recuperar el historial."
        ) from error