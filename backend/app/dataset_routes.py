from __future__ import annotations

import os
import re
import uuid
import jwt
from .services.auth_service import decode_guest_token
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .auth_dependencies import AuthPrincipal, get_current_principal
from .database import get_db
from .models import Dataset
from .rate_limiter import limiter

from .services.dataset_engine import (
    DatasetConnectionError,
    dispose_dataset_engine,
    get_dataset_engine,
)
from .services.dataset_import_engine import (
    DatasetImportConnectionError,
    get_dataset_import_engine,
)
from .services.dataset_foundry_service import (
    DatasetFoundryGenerationError,
    generate_dataset_sql,
)
from .services.dataset_service import (
    DatasetServiceError,
    create_dataset,
    get_accessible_dataset,
    list_datasets_for_guest,
    list_datasets_for_user,
    update_dataset_status,
)
from .services.dataset_sql_executor import (
    DatasetQueryExecutionError,
    execute_dataset_query,
)
from .services.dataset_sql_validator import (
    DatasetSQLValidationError,
    validate_dataset_sql,
)
from .services.history_service import (
    HistoryPersistenceError,
    get_recent_history,
    save_query_history,
)
from .services.schema_inspector import SchemaInspectionError, inspect_schema
from .services.sql_importer import SQLImportError, import_sql_script


router = APIRouter(prefix="/api/datasets", tags=["datasets"])
SCHEMA_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
MAX_UPLOAD_BYTES = 5_000_000


class DatasetSQLRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=10_000)


class DatasetAskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1_000)

class GuestClaimRequest(BaseModel):
    guest_token: str = Field(min_length=1, max_length=4096)

def _dataset_response(dataset: Dataset) -> dict[str, Any]:
    return {
        "dataset_id": dataset.dataset_id,
        "name": dataset.name,
        "original_filename": dataset.original_filename,
        "schema_name": dataset.schema_name,
        "status": dataset.status,
        "table_count": dataset.table_count,
        "row_count": dataset.row_count,
        "is_builtin": dataset.is_builtin,
        "error_message": dataset.error_message,
        "created_at": dataset.created_at,
    }


def _guest_dataset_expiration() -> datetime:
    """Alinea la expiración de los datasets con la del token invitado."""
    try:
        minutes = int(os.getenv("GUEST_TOKEN_EXPIRE_MINUTES", "720"))
    except ValueError as error:
        raise HTTPException(
            status_code=500,
            detail="La configuración de expiración de invitados no es válida.",
        ) from error

    if minutes < 15 or minutes > 1440:
        raise HTTPException(
            status_code=500,
            detail="La expiración de invitados debe estar entre 15 y 1440 minutos.",
        )

    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _get_dataset_or_404(
    db: Session,
    dataset_id: int,
    principal: AuthPrincipal,
) -> Dataset:
    try:
        dataset = get_accessible_dataset(
            db=db,
            dataset_id=dataset_id,
            owner_id=(
                principal.user.user_id
                if principal.user is not None
                else None
            ),
            guest_session_id=principal.guest_session_id,
        )
    except DatasetServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail="No se encontró el dataset solicitado.",
        )

    return dataset


@router.post("/upload")
@limiter.limit("5/hour")
async def upload_dataset(
    request: Request,
    name: str = Form(..., min_length=1, max_length=120),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    content = await file.read()
    await file.close()

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="El archivo SQL supera el tamaño máximo de 5 MB.",
        )

    schema_name = f"dataset_{uuid.uuid4().hex[:16]}"
    original_filename = file.filename or "dataset.sql"

    owner_id = (
        principal.user.user_id
        if principal.user is not None
        else None
    )
    guest_session_id = principal.guest_session_id

    expires_at = (
        _guest_dataset_expiration()
        if principal.is_guest
        else None
    )

    try:
        dataset = create_dataset(
            db=db,
            name=name.strip(),
            original_filename=original_filename,
            schema_name=schema_name,
            owner_id=owner_id,
            guest_session_id=guest_session_id,
            expires_at=expires_at,
        )

        try:
            imported = import_sql_script(
                content.decode("utf-8"),
                schema_name,
                dataset_id=dataset.dataset_id,
            )
        except UnicodeDecodeError as error:
            raise SQLImportError(
                "El archivo SQL debe utilizar codificación UTF-8."
            ) from error

        dataset = update_dataset_status(
            db=db,
            dataset_id=dataset.dataset_id,
            status="ready",
            table_count=imported["table_count"],
            row_count=imported["row_count"],
        )

        return {
            "success": True,
            **_dataset_response(dataset),
            "tables": imported["tables"],
        }

    except (DatasetServiceError, SQLImportError) as error:
        if "dataset" in locals() and dataset.dataset_id:
            try:
                update_dataset_status(
                    db=db,
                    dataset_id=dataset.dataset_id,
                    status="failed",
                    error_message=str(error),
                )
            except DatasetServiceError:
                db.rollback()

        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("")
def get_datasets(
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    try:
        if principal.user is not None:
            datasets = list_datasets_for_user(
                db,
                principal.user.user_id,
            )
        else:
            datasets = list_datasets_for_guest(
                db,
                principal.guest_session_id,
            )

        return {
            "success": True,
            "total": len(datasets),
            "items": [_dataset_response(dataset) for dataset in datasets],
        }

    except DatasetServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

@router.post("/claim-guest")
@limiter.limit("10/hour")
def claim_guest_datasets(
    request: Request,
    payload: GuestClaimRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    """
    Transfiere los datasets de una sesión de invitado
    a la cuenta registrada que solicita la operación.
    """

    if principal.user is None:
        raise HTTPException(
            status_code=403,
            detail="Debes iniciar sesión con una cuenta registrada.",
        )

    try:
        guest_session_id = decode_guest_token(payload.guest_token)
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="La sesión temporal es inválida o ha expirado.",
        )

    now = datetime.now(timezone.utc)

    try:
        datasets = (
            db.query(Dataset)
            .filter(
                Dataset.guest_session_id == guest_session_id,
                Dataset.owner_id.is_(None),
                Dataset.is_builtin.is_(False),
                (
                    Dataset.expires_at.is_(None)
                    | (Dataset.expires_at > now)
                ),
            )
            .with_for_update()
            .all()
        )

        transferred_ids = []

        for dataset in datasets:
            dataset.owner_id = principal.user.user_id
            dataset.guest_session_id = None
            dataset.expires_at = None
            transferred_ids.append(dataset.dataset_id)

        db.commit()

        return {
            "success": True,
            "message": "Transferencia de datasets completada.",
            "transferred_count": len(transferred_ids),
            "dataset_ids": transferred_ids,
        }

    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="No se pudieron transferir los datasets.",
        ) from error

@router.get("/{dataset_id}")
def get_dataset_details(
    dataset_id: int,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    return _dataset_response(
        _get_dataset_or_404(db, dataset_id, principal)
    )


@router.get("/{dataset_id}/schema")
@limiter.limit("60/minute")
def get_dataset_schema(
    request: Request,
    dataset_id: int,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    dataset = _get_dataset_or_404(db, dataset_id, principal)

    try:
        schema = inspect_schema(
            get_dataset_engine(dataset.dataset_id, dataset.schema_name),
            dataset.schema_name,
        )
        return {"success": True, **schema}

    except (DatasetConnectionError, SchemaInspectionError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/{dataset_id}/sql/validate")
@limiter.limit("60/minute")
def validate_dataset_sql_endpoint(
    request: Request,
    dataset_id: int,
    payload: DatasetSQLRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    dataset = _get_dataset_or_404(db, dataset_id, principal)

    try:
        schema = inspect_schema(
            get_dataset_engine(dataset.dataset_id, dataset.schema_name),
            dataset.schema_name,
        )
        validated_sql = validate_dataset_sql(payload.sql, schema)

        return {
            "success": True,
            "valid": True,
            "sql": validated_sql,
        }

    except (
        DatasetConnectionError,
        SchemaInspectionError,
        DatasetSQLValidationError,
    ) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{dataset_id}/sql/execute")
@limiter.limit("30/minute")
def execute_dataset_sql_endpoint(
    request: Request,
    dataset_id: int,
    payload: DatasetSQLRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    _get_dataset_or_404(db, dataset_id, principal)

    try:
        return execute_dataset_query(db, dataset_id, payload.sql)

    except (
        DatasetQueryExecutionError,
        DatasetConnectionError,
        SchemaInspectionError,
        DatasetSQLValidationError,
    ) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{dataset_id}/ask")
@limiter.limit("20/minute")
def ask_dataset(
    request: Request,
    dataset_id: int,
    payload: DatasetAskRequest,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    dataset = _get_dataset_or_404(db, dataset_id, principal)

    try:
        schema = inspect_schema(
            get_dataset_engine(dataset.dataset_id, dataset.schema_name),
            dataset.schema_name,
        )

        generated_sql = generate_dataset_sql(payload.question, schema)
        result = execute_dataset_query(db, dataset_id, generated_sql)

        history_id = None

        # Solo las cuentas registradas guardan historial permanente.
        if principal.user is not None:
            history_id = save_query_history(
                dataset_id=dataset_id,
                question=payload.question,
                generated_sql=result["sql"],
                row_count=result["row_count"],
                truncated=result["truncated"],
                result_columns=result["columns"],
                result_rows=result["rows"],
                user_id=principal.user.user_id,
            )

        return {
            **result,
            "history_id": history_id,
        }

    except (
        DatasetConnectionError,
        SchemaInspectionError,
        DatasetFoundryGenerationError,
        DatasetQueryExecutionError,
        HistoryPersistenceError,
    ) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/{dataset_id}/history")
def get_dataset_history(
    dataset_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    _get_dataset_or_404(db, dataset_id, principal)

    # Los invitados no tienen historial persistente.
    if principal.user is None:
        return {
            "success": True,
            "total": 0,
            "items": [],
        }

    try:
        items = get_recent_history(
            limit=limit,
            dataset_id=dataset_id,
            user_id=principal.user.user_id,
        )

        return {
            "success": True,
            "total": len(items),
            "items": items,
        }

    except HistoryPersistenceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    dataset = _get_dataset_or_404(db, dataset_id, principal)

    if dataset.is_builtin or dataset.schema_name == "public":
        raise HTTPException(
            status_code=403,
            detail="No se puede eliminar el dataset integrado.",
        )

    if not SCHEMA_PATTERN.fullmatch(dataset.schema_name):
        raise HTTPException(
            status_code=400,
            detail="El esquema del dataset no es válido.",
        )

    try:
        dispose_dataset_engine(dataset.dataset_id, dataset.schema_name)

        engine = get_dataset_import_engine()
        quoted_schema = engine.dialect.identifier_preparer.quote_identifier(
            dataset.schema_name
        )

        with engine.begin() as connection:
            # Retirar primero el esquema y después el rol, dentro de la misma
            # transacción: si alguna operación falla, PostgreSQL revierte ambas.
            connection.exec_driver_sql(
                f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE"
            )
            connection.execute(
                text("SELECT datamind_security.drop_dataset_reader(:dataset_id)"),
                {"dataset_id": dataset.dataset_id},
            )

        db.delete(dataset)
        db.commit()

        return {
            "success": True,
            "message": "Dataset eliminado correctamente.",
            "dataset_id": dataset_id,
        }

    except (
        DatasetImportConnectionError,
        DatasetConnectionError,
        SQLAlchemyError,
    ) as error:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="No se pudo eliminar completamente el dataset.",
        ) from error