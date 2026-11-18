from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

SYSTEM_INSTRUCTIONS = """
Eres el generador de consultas SQL de DataMind AI.
Convierte preguntas en español en una única consulta SELECT válida para PostgreSQL.
Usa exclusivamente las tablas, columnas y relaciones del esquema proporcionado.
No inventes tablas ni columnas. No uses INSERT, UPDATE, DELETE, DROP, ALTER, CREATE,
COPY, funciones administrativas ni esquemas del sistema.
Devuelve únicamente SQL, sin explicaciones ni bloques Markdown.
"""


class DatasetFoundryGenerationError(RuntimeError):
    """Error al generar SQL dinámico mediante Microsoft Foundry."""


def build_schema_context(schema_info: dict[str, Any]) -> str:
    """Format inspected schema metadata as model context."""
    lines = [
        f"ESQUEMA SELECCIONADO: {schema_info.get('schema_name', '')}",
        "TABLAS Y COLUMNAS:",
    ]
    for table in schema_info.get("tables", []):
        lines.append(f"- {table['name']}:")
        for column in table.get("columns", []):
            nullable = "NULL" if column.get("nullable") else "NOT NULL"
            lines.append(
                f"  - {column['name']} ({column.get('type', 'unknown')}, {nullable})"
            )
        primary_key = table.get("primary_key", [])
        if primary_key:
            lines.append(f"  PK: {', '.join(primary_key)}")
        for foreign_key in table.get("foreign_keys", []):
            source = ", ".join(foreign_key.get("columns", []))
            target = ".".join(
                part
                for part in (
                    foreign_key.get("referenced_schema"),
                    foreign_key.get("referenced_table"),
                )
                if part
            )
            target_columns = ", ".join(
                foreign_key.get("referenced_columns", [])
            )
            lines.append(f"  FK: {source} -> {target} ({target_columns})")
    return "\n".join(lines)


def generate_dataset_sql(
    question: str,
    schema_info: dict[str, Any],
) -> str:
    """Generate a SQL query using only the selected dataset schema."""
    if not question or not question.strip():
        raise DatasetFoundryGenerationError("La pregunta está vacía.")
    if len(question) > 1000:
        raise DatasetFoundryGenerationError(
            "La pregunta supera el tamaño permitido."
        )

    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model = os.getenv("FOUNDRY_MODEL")
    if not endpoint or not model:
        raise DatasetFoundryGenerationError(
            "Falta configurar el endpoint o modelo de Foundry."
        )

    schema_context = build_schema_context(schema_info)
    try:
        with DefaultAzureCredential() as credential:
            with AIProjectClient(
                endpoint=endpoint,
                credential=credential,
            ) as project:
                with project.get_openai_client() as client:
                    response = client.responses.create(
                        model=model,
                        instructions=(
                            SYSTEM_INSTRUCTIONS
                            + "\n\n"
                            + schema_context
                        ),
                        input=question,
                        max_output_tokens=700,
                    )
                    sql = response.output_text.strip()
                    if sql.startswith("```"):
                        sql = re.sub(
                            r"^```(?:sql)?\s*|\s*```$",
                            "",
                            sql,
                            flags=re.IGNORECASE,
                        ).strip()
                    if not sql:
                        raise DatasetFoundryGenerationError(
                            "El modelo no generó una consulta SQL."
                        )
                    return sql
    except DatasetFoundryGenerationError:
        raise
    except Exception as error:
        raise DatasetFoundryGenerationError(
            "No se pudo generar SQL mediante Microsoft Foundry."
        ) from error
