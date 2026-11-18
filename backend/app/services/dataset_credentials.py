from __future__ import annotations

import hashlib
import hmac
import os


class DatasetCredentialError(RuntimeError):
    """Error de configuración o derivación de credenciales de datasets."""


def dataset_reader_role_name(dataset_id: int) -> str:
    if not isinstance(dataset_id, int) or isinstance(dataset_id, bool) or dataset_id <= 0:
        raise DatasetCredentialError("El identificador del dataset no es válido.")
    return f"dm_reader_ds_{dataset_id}"


def derive_dataset_reader_password(dataset_id: int) -> str:
    """Deriva una contraseña estable por dataset sin almacenarla en PostgreSQL."""
    role_name = dataset_reader_role_name(dataset_id)
    secret = os.getenv("DATASET_ROLE_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        raise DatasetCredentialError(
            "DATASET_ROLE_SECRET debe contener al menos 32 bytes."
        )

    message = f"datamind-ai:dataset-reader:v1:{role_name}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
