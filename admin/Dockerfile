FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=4000

WORKDIR /app

# Install git or clean dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy shared library first
COPY shared/ ./shared/
RUN pip install ./shared

# Copy admin configuration files
COPY admin/pyproject.toml admin/README.md ./
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install .

# Copy admin source files
COPY admin/ .

# Copy Kubernetes city manifests so they can be templated and deployed
COPY infra/k8s/city/ ./infra/k8s/city/

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
