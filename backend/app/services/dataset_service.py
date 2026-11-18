from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import Dataset


VALID_STATUSES = {"processing", "ready", "failed"}


class DatasetServiceError(RuntimeError):
    """Error al crear, listar o actualizar datasets."""


def create_dataset(
    db: Session,
    name: str,
    original_filename: str,
    schema_name: str,
    owner_id: int | None = None,
    guest_session_id: UUID | None = None,
    expires_at: datetime | None = None,
    status: str = "processing",
) -> Dataset:
    """Crea un dataset asociado a un usuario o a un invitado."""

    if not name or not original_filename:
        raise DatasetServiceError(
            "El nombre y el archivo original son obligatorios."
        )

    if (owner_id is None) == (guest_session_id is None):
        raise DatasetServiceError(
            "El dataset debe pertenecer a un usuario o a un invitado."
        )

    if status not in VALID_STATUSES:
        raise DatasetServiceError("El estado del dataset no es válido.")

    dataset = Dataset(
        name=name,
        original_filename=original_filename,
        schema_name=schema_name,
        owner_id=owner_id,
        guest_session_id=guest_session_id,
        expires_at=expires_at,
        status=status,
    )

    db.add(dataset)

    try:
        db.commit()
        db.refresh(dataset)
        return dataset
    except SQLAlchemyError as error:
        db.rollback()
        raise DatasetServiceError(
            "No se pudo crear el dataset."
        ) from error


def get_dataset(db: Session, dataset_id: int) -> Dataset | None:
    """Obtiene un dataset por su identificador."""

    try:
        return db.get(Dataset, dataset_id)
    except SQLAlchemyError as error:
        raise DatasetServiceError(
            "No se pudo recuperar el dataset."
        ) from error


def list_datasets(
    db: Session,
    owner_id: int | None = None,
) -> list[Dataset]:
    """Lista datasets integrados y, opcionalmente, los de un usuario."""

    try:
        query = select(Dataset)

        if owner_id is not None:
            query = query.where(
                or_(
                    Dataset.is_builtin.is_(True),
                    Dataset.owner_id == owner_id,
                )
            )

        return list(
            db.scalars(
                query.order_by(
                    Dataset.created_at.desc(),
                    Dataset.dataset_id.desc(),
                )
            ).all()
        )

    except SQLAlchemyError as error:
        raise DatasetServiceError(
            "No se pudieron recuperar los datasets."
        ) from error


def list_datasets_for_user(
    db: Session,
    owner_id: int,
) -> list[Dataset]:
    """Lista únicamente los datasets integrados y propios del usuario."""

    return list_datasets(db, owner_id)


def list_datasets_for_guest(
    db: Session,
    guest_session_id: UUID,
) -> list[Dataset]:
    """Lista el dataset integrado y los datasets vigentes del invitado."""

    try:
        guest_condition = and_(
            Dataset.guest_session_id == guest_session_id,
            or_(
                Dataset.expires_at.is_(None),
                Dataset.expires_at > func.now(),
            ),
        )

        query = select(Dataset).where(
            or_(
                Dataset.is_builtin.is_(True),
                guest_condition,
            )
        )

        return list(
            db.scalars(
                query.order_by(
                    Dataset.created_at.desc(),
                    Dataset.dataset_id.desc(),
                )
            ).all()
        )

    except SQLAlchemyError as error:
        raise DatasetServiceError(
            "No se pudieron recuperar los datasets del invitado."
        ) from error


def get_accessible_dataset(
    db: Session,
    dataset_id: int,
    owner_id: int | None = None,
    guest_session_id: UUID | None = None,
) -> Dataset | None:
    """Obtiene un dataset integrado o perteneciente a la identidad actual."""

    try:
        ownership_conditions = [
            Dataset.is_builtin.is_(True)
        ]

        if owner_id is not None:
            ownership_conditions.append(
                Dataset.owner_id == owner_id
            )

        if guest_session_id is not None:
            ownership_conditions.append(
                and_(
                    Dataset.guest_session_id == guest_session_id,
                    or_(
                        Dataset.expires_at.is_(None),
                        Dataset.expires_at > func.now(),
                    ),
                )
            )

        return db.scalar(
            select(Dataset).where(
                Dataset.dataset_id == dataset_id,
                or_(*ownership_conditions),
            )
        )

    except SQLAlchemyError as error:
        raise DatasetServiceError(
            "No se pudo recuperar el dataset."
        ) from error


def update_dataset_status(
    db: Session,
    dataset_id: int,
    status: str,
    table_count: int = 0,
    row_count: int = 0,
    error_message: str | None = None,
) -> Dataset:
    """Actualiza el estado y las estadísticas del dataset."""

    if status not in VALID_STATUSES:
        raise DatasetServiceError("El estado del dataset no es válido.")

    if table_count < 0 or row_count < 0:
        raise DatasetServiceError(
            "Las cantidades no pueden ser negativas."
        )

    dataset = get_dataset(db, dataset_id)

    if dataset is None:
        raise DatasetServiceError("No se encontró el dataset solicitado.")

    dataset.status = status
    dataset.table_count = table_count
    dataset.row_count = row_count
    dataset.error_message = error_message

    try:
        db.commit()
        db.refresh(dataset)
        return dataset
    except SQLAlchemyError as error:
        db.rollback()
        raise DatasetServiceError(
            "No se pudo actualizar el estado del dataset."
        ) from error