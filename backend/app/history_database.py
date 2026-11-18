import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

username = os.getenv("HISTORY_DB_USER")
password = os.getenv("HISTORY_DB_PASSWORD")

if not username or not password:
    raise RuntimeError(
        "Faltan las credenciales HISTORY_DB_USER o HISTORY_DB_PASSWORD."
    )

database_url = URL.create(
    drivername="postgresql+psycopg",
    username=username,
    password=password,
    host=os.getenv("HISTORY_DB_HOST", "localhost"),
    port=int(os.getenv("HISTORY_DB_PORT", "5432")),
    database=os.getenv("HISTORY_DB_NAME", "datamind_db"),
)

history_engine = create_engine(
    database_url,
    pool_pre_ping=True
)