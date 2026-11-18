import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .database import get_db
from .auth_dependencies import get_current_active_user
from .models import Customer, Product, Order, OrderDetail, Payment, User
from .database import engine
from pydantic import BaseModel, Field
from fastapi import Query
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from .auth_routes import router as auth_router
from .dataset_routes import router as dataset_router
from .rate_limiter import limiter

from .services.history_service import (
    save_query_history,
    get_recent_history,
    HistoryPersistenceError
)
from .services.guest_cleanup_service import cleanup_expired_guest_datasets

from .services.sql_validator import (
    validate_readonly_sql,
    SQLValidationError,
    execute_readonly_query,
    QueryExecutionError
)

from .services.foundry_service import (
    generate_sql,
    FoundryGenerationError
)

from .services.sql_executor import (
    execute_readonly_query,
    QueryExecutionError
)

class SQLValidationRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=10000)

class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)

SQLExecutionRequest = SQLValidationRequest

logger = logging.getLogger(__name__)


async def guest_cleanup_worker():
    """
    Limpia datasets temporales vencidos al iniciar y posteriormente cada hora.
    """
    while True:
        try:
            deleted_count = await asyncio.to_thread(
                cleanup_expired_guest_datasets,
                batch_size=50,
            )
            if deleted_count:
                logger.info(
                    "Limpieza automática: %s datasets temporales eliminados.",
                    deleted_count,
                )
        except Exception:
            logger.exception(
                "Error en la limpieza automática de datasets temporales."
            )
        await asyncio.sleep(3600)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(
        guest_cleanup_worker(),
        name="guest-dataset-cleanup",
    )
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


app = FastAPI(
    title="DataMind AI API",
    description="API para el análisis de datos empresariales mediante IA",
    version="1.0.0",
    lifespan=app_lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
)

app.include_router(auth_router)

# Permitir solicitudes desde Angular
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "message": "DataMind AI API funcionando correctamente"
    }

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "message": "Backend conectado correctamente"
    }

@app.get("/api/db-health")
def database_health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "ok",
            "database": "connected",
            "message": "PostgreSQL conectado correctamente"
        }

    except SQLAlchemyError as error:
        print(f"Error de conexión con PostgreSQL: {error}")

        raise HTTPException(
            status_code=503,
            detail="No se pudo conectar con PostgreSQL. Revisa backend/.env."
        ) from error

@app.get("/api/data-summary")
def data_summary(db: Session = Depends(get_db)):

    return {
        "customers": db.scalar(
            select(func.count()).select_from(Customer)
        ) or 0,

        "products": db.scalar(
            select(func.count()).select_from(Product)
        ) or 0,

        "orders": db.scalar(
            select(func.count()).select_from(Order)
        ) or 0,

        "order_details": db.scalar(
            select(func.count()).select_from(OrderDetail)
        ) or 0,

        "payments": db.scalar(
            select(func.count()).select_from(Payment)
        ) or 0
    }

@app.post("/api/sql/validate")
def validate_sql_endpoint(request: SQLValidationRequest):

    try:
        validated_sql = validate_readonly_sql(request.sql)

        return {
            "valid": True,
            "message": "Consulta SQL validada correctamente.",
            "sql": validated_sql
        }

    except SQLValidationError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

@app.post("/api/sql/execute")
def execute_sql_endpoint(request: SQLExecutionRequest):

    try:

        return execute_readonly_query(request.sql)

    except SQLValidationError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except QueryExecutionError as error:

        raise HTTPException(
            status_code=422,
            detail=str(error)
        )

@app.post("/api/ask")
def ask_data(request: AskRequest, user: User = Depends(get_current_active_user)):

    try:
        # 1. Generar SQL utilizando GPT-4.1 mini.
        generated_sql = generate_sql(request.question)

        # 2. Validar y ejecutar la consulta.
        result = execute_readonly_query(generated_sql)

        history_id = save_query_history(
            dataset_id=1,
            question=request.question,
            generated_sql=result["sql"],
            row_count=result["row_count"],
            truncated=result["truncated"],
            result_columns=result["columns"],
            result_rows=result["rows"],
            user_id=user.user_id,
        )

        # 3. Devolver la respuesta estructurada.
        return {
            "success": True,
            "question": request.question,
            "history_id": history_id,
            "sql": result["sql"],
            "columns": result["columns"],
            "rows": result["rows"],
            "row_count": result["row_count"],
            "truncated": result["truncated"]
        }

    except FoundryGenerationError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error)
        ) from error

    except SQLValidationError as error:
        raise HTTPException(
            status_code=422,
            detail=f"Consulta generada rechazada: {error}"
        ) from error

    except QueryExecutionError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error

    except HistoryPersistenceError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error)
        ) from error

@app.get("/api/history")
def get_history(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_active_user),
):
    try:
        items = get_recent_history(limit=limit, user_id=user.user_id)

        return {
            "success": True,
            "total": len(items),
            "items": items
        }

    except HistoryPersistenceError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error)
        ) from error


app.include_router(dataset_router)
