import json

from sqlalchemy import text

from app.history_database import history_engine
from app.services.sql_executor import execute_readonly_query


def backfill_history():

    with history_engine.connect() as connection:
        records = connection.execute(
            text("""
                SELECT
                    history_id,
                    generated_sql
                FROM public.query_history
                WHERE result_rows = '[]'::jsonb
                  AND row_count > 0
                ORDER BY history_id
            """)
        ).mappings().all()

    print(f"Registros por reconstruir: {len(records)}")

    for record in records:

        history_id = record["history_id"]

        try:
            result = execute_readonly_query(
                record["generated_sql"]
            )

            with history_engine.begin() as connection:

                connection.execute(
                    text("""
                        UPDATE public.query_history
                        SET
                            result_columns = CAST(
                                :result_columns AS jsonb
                            ),
                            result_rows = CAST(
                                :result_rows AS jsonb
                            ),
                            row_count = :row_count,
                            truncated = :truncated
                        WHERE history_id = :history_id
                    """),
                    {
                        "history_id": history_id,
                        "result_columns": json.dumps(
                            result["columns"],
                            ensure_ascii=False
                        ),
                        "result_rows": json.dumps(
                            result["rows"],
                            ensure_ascii=False
                        ),
                        "row_count": result["row_count"],
                        "truncated": result["truncated"]
                    }
                )

            print(f"OK: Consulta #{history_id} reconstruida.")

        except Exception as error:
            print(
                f"ERROR: Consulta #{history_id}: "
                f"{type(error).__name__}: {error}"
            )


if __name__ == "__main__":
    backfill_history()