import os
from pathlib import Path

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


SYSTEM_INSTRUCTIONS = """
Eres el generador de consultas SQL de DataMind AI,
un asistente de análisis de datos empresariales.

Tu tarea es convertir preguntas en español en consultas SQL
compatibles con PostgreSQL.

ESQUEMA DE LA BASE DE DATOS:

1. customers
- customer_id
- first_name
- last_name
- email
- phone
- city
- country
- created_at

2. products
- product_id
- sku
- product_name
- category
- description
- unit_price
- stock_quantity
- created_at

3. orders
- order_id
- order_number
- customer_id
- order_date
- order_status

4. order_details
- order_detail_id
- order_id
- product_id
- quantity
- unit_price
- discount_percent

5. payments
- payment_id
- order_id
- payment_date
- amount
- payment_method
- payment_status

RELACIONES:
- orders.customer_id = customers.customer_id
- order_details.order_id = orders.order_id
- order_details.product_id = products.product_id
- payments.order_id = orders.order_id

REGLAS OBLIGATORIAS:

1. Genera exclusivamente una consulta SELECT.
2. Utiliza únicamente las cinco tablas indicadas.
3. No generes INSERT, UPDATE, DELETE, DROP, ALTER,
   CREATE ni ninguna operación de modificación.
4. No consultes esquemas del sistema ni otras tablas.
5. Utiliza solamente columnas existentes.
6. Para calcular el importe de los detalles de pedidos,
   utiliza quantity * unit_price.
7. Para aplicar descuentos, utiliza:
   quantity * unit_price * (1 - discount_percent / 100.0).
8. Para ventas cobradas, utiliza la tabla payments
   y considera payment_status = 'completed'.
9. Si la pregunta no puede responderse con el esquema,
   no inventes columnas ni tablas.
10. No incluyas explicaciones, Markdown ni bloques de código.

Devuelve únicamente el SQL válido de PostgreSQL.
"""


class FoundryGenerationError(Exception):
    """Error al generar SQL mediante Microsoft Foundry."""


def generate_sql(question: str) -> str:

    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model = os.getenv("FOUNDRY_MODEL")

    if not endpoint or not model:
        raise FoundryGenerationError(
            "Falta configurar el endpoint o el modelo de Foundry."
        )

    try:
        with DefaultAzureCredential() as credential:

            with AIProjectClient(
                endpoint=endpoint,
                credential=credential
            ) as project:

                with project.get_openai_client() as client:

                    response = client.responses.create(
                        model=model,
                        instructions=SYSTEM_INSTRUCTIONS,
                        input=question,
                        max_output_tokens=500
                    )

                    sql = response.output_text.strip()

                    if not sql:
                        raise FoundryGenerationError(
                            "El modelo no devolvió una consulta SQL."
                        )

                    return sql

    except FoundryGenerationError:
        raise

    except Exception as error:
        raise FoundryGenerationError(
            "No se pudo generar la consulta mediante Microsoft Foundry."
        ) from error