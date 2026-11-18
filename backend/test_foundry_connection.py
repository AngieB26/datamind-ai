import os
from pathlib import Path

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.core.exceptions import HttpResponseError

load_dotenv(Path(__file__).resolve().parent / ".env")

endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")

if not endpoint:
    raise ValueError("Falta FOUNDRY_PROJECT_ENDPOINT en .env")

try:
    with DefaultAzureCredential() as credential:
        with AIProjectClient(
            endpoint=endpoint,
            credential=credential
        ) as project:

            print("Consultando deployments de Microsoft Foundry...")

            deployments = list(project.deployments.list())

            print("\nAcceso remoto validado correctamente.")

            if deployments:
                print("\nModelos disponibles:")

                for deployment in deployments:
                    print(deployment)
            else:
                print("\nTodavía no hay modelos desplegados.")

except HttpResponseError as error:
    print(f"Error HTTP: {error.status_code}")
    print(error.message)

except Exception as error:
    print(f"Error: {type(error).__name__}: {error}")