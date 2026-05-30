FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=4004

WORKDIR /app

COPY pyproject.toml README.md ./
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install .

COPY . .

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
