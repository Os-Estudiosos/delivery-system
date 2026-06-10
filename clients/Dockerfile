FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=4001

WORKDIR /app

COPY shared/ ./shared/
RUN pip install ./shared

COPY clients/pyproject.toml clients/README.md ./
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install .

COPY clients/ .

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]