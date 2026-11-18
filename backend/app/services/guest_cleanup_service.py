
from __future__ import annotations

import logging
import re

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..history_database import history_engine
from ..models import Dataset
from .dataset_engine import dispose_dataset_engine
from .dataset_import_engine import get_dataset_import_engine


logger = logging.getLogger(__name__)

SCHEMA_PATTERN = re.compile(r"^dataset_[a-f0-9]{12,32}$")


def _has_history(dataset_id: int) -> bool:
    """Comprueba si existen consultas históricas asociadas al dataset."""
    with history_engine.connect() as connection:
        result = connection.execute(
            text("""
                SELECT COUNT(*)
                FROM public.query_history
                WHERE dataset_id = :dataset_id
            """),
            {"dataset_id": dataset_id},
        )
        return result.scalar_one() > 0


def cleanup_expired_guest_datasets(batch_size: int = 50) -> int:
    """
    Elimina datasets temporales vencidos de invitados.

    Protecciones:
    - No elimina datasets de usuarios registrados.
    - No elimina datasets integrados.
    - No elimina datasets con historial de usuarios registrados.
    - Solo utiliza nombres de esquema validados.
    """

    if not 1 <= batch_size <= 500:
        raise ValueError("batch_size debe estar entre 1 y 500.")

    db: Session = SessionLocal()
    deleted_count = 0

    try:
        expired_datasets = (
            db.query(Dataset)
            .filter(
                Dataset.owner_id.is_(None),
                Dataset.guest_session_id.is_not(None),
                Dataset.expires_at.is_not(None),
                Dataset.expires_at <= func.now(),
                Dataset.is_builtin.is_(False),
            )
            .order_by(Dataset.expires_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
            .all()
        )

        for dataset in expired_datasets:
            dataset_id = dataset.dataset_id
            schema_name = dataset.schema_name

            if not SCHEMA_PATTERN.fullmatch(schema_name):
                logger.error(
                    "Esquema inválido. Se omite el dataset %s.",
                    dataset_id,
                )
                continue

            try:
                # Protección adicional para el historial permanente.
                if _has_history(dataset_id):
                    logger.warning(
                        "Se omite el dataset %s porque tiene "
                        "historial asociado a un usuario registrado.",
                        dataset_id,
                    )
                    continue

                # Cerrar las conexiones del esquema.
                dispose_dataset_engine(dataset_id, schema_name)

                # Eliminar el esquema con el usuario de importación.
                import_engine = get_dataset_import_engine()

                quoted_schema = (
                    import_engine.dialect.identifier_preparer
                    .quote_identifier(schema_name)
                )

                with import_engine.begin() as connection:
                    # Mantener la eliminación del esquema y del rol en una
                    # sola transacción para evitar estados parciales.
                    connection.exec_driver_sql(
                        f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE"
                    )
                    connection.execute(
                        text("SELECT datamind_security.drop_dataset_reader(:dataset_id)"),
                        {"dataset_id": dataset_id},
                    )

                # PostgreSQL aplicará ON DELETE CASCADE al historial.
                # La comprobación anterior garantiza que no haya
                # historial persistente de usuarios registrados.
                db.delete(dataset)
                db.commit()

                deleted_count += 1

                logger.info(
                    "Dataset temporal eliminado: %s",
                    dataset_id,
                )

            except Exception:
                db.rollback()

                logger.exception(
                    "No se pudo eliminar el dataset temporal %s.",
                    dataset_id,
                )

        return deleted_count

    except Exception:
        db.rollback()
        logger.exception(
            "Error durante la limpieza de datasets temporales."
        )
        raise

    finally:
        db.close()
