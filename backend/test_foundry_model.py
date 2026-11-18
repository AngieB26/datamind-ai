import os
from pathlib import Path

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

load_dotenv(Path(__file__).resolve().parent / ".env")

endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
model = os.getenv("FOUNDRY_MODEL")

if not endpoint or not model:
    raise ValueError("Falta configurar el endpoint o modelo.")

credential = DefaultAzureCredential()

project = AIProjectClient(
    endpoint=endpoint,
    credential=credential
)

try:
    client = project.get_openai_client()

    response = client.responses.create(
        model=model,
        input="Responde únicamente: DataMind AI está conectado correctamente.",
        max_output_tokens=40
    )

    print("Respuesta de Microsoft Foundry:")
    print(response.output_text)

finally:
    project.close()
    credential.close()