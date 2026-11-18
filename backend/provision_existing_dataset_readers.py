from __future__ import annotations

import re
import sys

from sqlalchemy import func, or_, text

from app.database import SessionLocal
from app.models import Dataset
from app.services.dataset_credentials import (
    DatasetCredentialError,
    derive_dataset_reader_password,
)
from app.services.dataset_import_engine import get_dataset_import_engine


SCHEMA_PATTERN = re.compile(r"^dataset_[a-f0-9]{12,32}$")
PROVISION_SQL = text(
    """SELECT datamind_security.provision_dataset_reader(
        :dataset_id, :schema_name, :password
    )"""
)


def main() -> int:
    try:
        with SessionLocal() as db:
            datasets = (
                db.query(Dataset)
                .filter(
                    Dataset.is_builtin.is_(False),
                    Dataset.status == "ready",
                    (Dataset.owner_id.is_not(None) | Dataset.guest_session_id.is_not(None)),
                    or_(Dataset.expires_at.is_(None), Dataset.expires_at > func.now()),
                )
                .order_by(Dataset.dataset_id)
                .all()
            )

        if not datasets:
            print("No hay datasets privados listos para migrar.")
            return 0

        import_engine = get_dataset_import_engine()
        failures: list[tuple[int, str]] = []
        for dataset in datasets:
            if not SCHEMA_PATTERN.fullmatch(dataset.schema_name):
                failures.append((dataset.dataset_id, "nombre de esquema no válido"))
                continue
            try:
                password = derive_dataset_reader_password(dataset.dataset_id)
                with import_engine.begin() as connection:
                    role_name = connection.execute(
                        PROVISION_SQL,
                        {
                            "dataset_id": dataset.dataset_id,
                            "schema_name": dataset.schema_name,
                            "password": password,
                        },
                    ).scalar_one()
                print(f"OK dataset_id={dataset.dataset_id} rol={role_name}")
            except Exception as error:
                failures.append((dataset.dataset_id, str(error).splitlines()[0][:180]))

        if failures:
            print("\nDatasets que requieren revisión:")
            for dataset_id, reason in failures:
                print(f"- dataset_id={dataset_id}: {reason}")
            return 1

        print(f"\nMigración completada: {len(datasets)} roles individuales provisionados.")
        return 0
    except DatasetCredentialError as error:
        print(f"ERROR de credenciales: {error}")
        return 2
    except Exception as error:
        print(f"ERROR: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
