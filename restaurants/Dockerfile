FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=4005

WORKDIR /app

COPY shared/ ./shared/
RUN pip install ./shared

COPY restaurants/ ./restaurants/
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install ./restaurants

CMD ["sh", "-c", "uvicorn restaurants.main:app --host 0.0.0.0 --port ${PORT}"]