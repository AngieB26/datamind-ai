from __future__ import annotations

import re
from threading import RLock

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from ..database import engine as base_engine
from .dataset_credentials import (
    DatasetCredentialError,
    dataset_reader_role_name,
    derive_dataset_reader_password,
)


class DatasetConnectionError(RuntimeError):
    """Error al crear o liberar la conexión de un dataset."""


_engines: dict[tuple[int, str], Engine] = {}
_engines_lock = RLock()
_SCHEMA_PATTERN = re.compile(r"^dataset_[a-f0-9]{12,32}$")


def _validate_dataset(dataset_id: int, schema_name: str) -> None:
    if not isinstance(dataset_id, int) or isinstance(dataset_id, bool) or dataset_id <= 0:
        raise DatasetConnectionError("El identificador del dataset no es válido.")
    if schema_name != "public" and not _SCHEMA_PATTERN.fullmatch(schema_name):
        raise DatasetConnectionError("El esquema no es válido.")


def get_dataset_engine(dataset_id: int, schema_name: str) -> Engine:
    """Obtiene una conexión pública o una conexión privada por rol de dataset."""
    _validate_dataset(dataset_id, schema_name)
    cache_key = (dataset_id, schema_name)

    with _engines_lock:
        cached_engine = _engines.get(cache_key)
        if cached_engine is not None:
            return cached_engine

        try:
            if schema_name == "public":
                database_url = base_engine.url
            else:
                database_url = base_engine.url.set(
                    username=dataset_reader_role_name(dataset_id),
                    password=derive_dataset_reader_password(dataset_id),
                )

            dataset_engine = create_engine(
                database_url,
                pool_pre_ping=True,
                connect_args={
                    "options": f"-csearch_path={schema_name},pg_catalog"
                },
            )
            _engines[cache_key] = dataset_engine
            return dataset_engine
        except Exception as error:
            raise DatasetConnectionError(
                "No se pudo establecer la conexión aislada al dataset."
            ) from error


def dispose_dataset_engine(dataset_id: int, schema_name: str) -> None:
    """Cierra y elimina del caché la conexión del dataset indicado."""
    _validate_dataset(dataset_id, schema_name)
    with _engines_lock:
        dataset_engine = _engines.pop((dataset_id, schema_name), None)
        if dataset_engine is not None:
            dataset_engine.dispose()


def dispose_all_dataset_engines() -> None:
    """Cierra todas las conexiones de datasets."""
    with _engines_lock:
        engines = list(_engines.values())
        _engines.clear()
        for dataset_engine in engines:
            dataset_engine.dispose()
