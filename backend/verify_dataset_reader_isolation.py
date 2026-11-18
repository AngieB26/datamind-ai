from __future__ import annotations

from sqlalchemy import create_engine, func, inspect, or_, text
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal, engine as base_engine
from app.models import Dataset
from app.services.dataset_credentials import (
    derive_dataset_reader_password,
    dataset_reader_role_name,
)
from app.services.dataset_import_engine import get_dataset_import_engine


def main() -> int:
    with SessionLocal() as db:
        datasets = (
            db.query(Dataset.dataset_id, Dataset.schema_name)
            .filter(
                Dataset.is_builtin.is_(False),
                Dataset.status == "ready",
                (Dataset.owner_id.is_not(None) | Dataset.guest_session_id.is_not(None)),
                or_(Dataset.expires_at.is_(None), Dataset.expires_at > func.now()),
            )
            .all()
        )

    if not datasets:
        print("No hay datasets privados listos para verificar.")
        return 0

    importer_engine = get_dataset_import_engine()
    inspector = inspect(importer_engine)
    tables_by_schema = {
        schema_name: sorted(inspector.get_table_names(schema=schema_name))
        for _, schema_name in datasets
    }
    quote = importer_engine.dialect.identifier_preparer.quote_identifier
    failures: list[str] = []
    passed = 0

    for dataset_id, schema_name in datasets:
        role_name = dataset_reader_role_name(dataset_id)
        reader_engine = None
        try:
            if not tables_by_schema[schema_name]:
                raise RuntimeError("el esquema no contiene tablas")

            reader_engine = create_engine(
                base_engine.url.set(
                    username=role_name,
                    password=derive_dataset_reader_password(dataset_id),
                ),
                pool_pre_ping=True,
            )

            with reader_engine.connect() as connection:
                actual_role = connection.execute(
                    text("SELECT current_user")
                ).scalar_one()
                if actual_role != role_name:
                    raise RuntimeError(f"current_user inesperado: {actual_role}")
                first_table = tables_by_schema[schema_name][0]
                connection.exec_driver_sql(
                    f"SELECT COUNT(*) FROM {quote(schema_name)}.{quote(first_table)}"
                ).scalar_one()

            unauthorized_access = None
            for other_schema, other_tables in tables_by_schema.items():
                if other_schema == schema_name or not other_tables:
                    continue
                try:
                    with reader_engine.connect() as connection:
                        connection.exec_driver_sql(
                            f"SELECT 1 FROM {quote(other_schema)}.{quote(other_tables[0])} LIMIT 1"
                        ).fetchone()
                except SQLAlchemyError:
                    continue
                unauthorized_access = other_schema
                break

            if unauthorized_access is not None:
                raise RuntimeError(
                    f"puede leer indebidamente el esquema {unauthorized_access}"
                )

            passed += 1
            print(
                f"OK dataset_id={dataset_id}: lectura propia permitida; "
                "otros esquemas bloqueados"
            )
        except Exception as error:
            failures.append(
                f"dataset_id={dataset_id}: {str(error).splitlines()[0][:200]}"
            )
            print(f"ERROR dataset_id={dataset_id}: {str(error).splitlines()[0][:200]}")
        finally:
            if reader_engine is not None:
                reader_engine.dispose()

    print(f"\nResultado: {passed}/{len(datasets)} roles verificados correctamente.")
    if failures:
        print("No revoques todavía los permisos globales de datamind_reader.")
        return 1
    print(
        "Verificación completada. Conserva el lector compartido hasta terminar "
        "las pruebas funcionales."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
