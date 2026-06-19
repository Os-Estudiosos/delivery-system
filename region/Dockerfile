FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=4006

WORKDIR /app

COPY shared/ ./shared/
RUN pip install ./shared

COPY region/pyproject.toml region/README.md ./
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install .

COPY region/ .

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS:-4}"]