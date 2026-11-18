from __future__ import annotations

import os
from threading import RLock

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine


class DatasetImportConnectionError(RuntimeError):
    """Error al configurar el motor de importación."""


_import_engine: Engine | None = None
_engine_lock = RLock()


def get_dataset_import_engine() -> Engine:
    """Obtiene o crea el motor con credenciales de importación separadas."""
    global _import_engine

    with _engine_lock:
        if _import_engine is not None:
            return _import_engine

        username = os.getenv("DATASET_IMPORT_DB_USER")
        password = os.getenv("DATASET_IMPORT_DB_PASSWORD")
        if not username or not password:
            raise DatasetImportConnectionError(
                "Faltan las credenciales del usuario de importación."
            )

        database_url = URL.create(
            drivername="postgresql+psycopg",
            username=username,
            password=password,
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "datamind_db"),
        )

        try:
            _import_engine = create_engine(
                database_url,
                pool_pre_ping=True,
                pool_size=2,
                max_overflow=2,
                pool_recycle=1800,
            )
            return _import_engine
        except Exception as error:
            raise DatasetImportConnectionError(
                "No se pudo configurar la conexión de importación."
            ) from error


def dispose_dataset_import_engine() -> None:
    """Cierra el motor de importación."""
    global _import_engine

    with _engine_lock:
        if _import_engine is not None:
            _import_engine.dispose()
            _import_engine = None
