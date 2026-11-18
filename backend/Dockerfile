FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV AZURE_CONFIG_DIR=/home/appuser/.azure

WORKDIR /app

# Instalar dependencias del sistema y Azure CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    gnupg \
    apt-transport-https \
    lsb-release \
    && curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias de Python
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copiar aplicación
COPY app/ ./app/

# Crear usuario sin privilegios de administrador
RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /home/appuser/.azure \
    && chown -R appuser:appuser /home/appuser

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]