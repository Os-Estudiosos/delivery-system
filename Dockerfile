FROM python:3.12-slim

# Evita gerar .pyc e buffer de stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala uv
RUN pip install uv

WORKDIR /app

# Copia apenas dependências primeiro (cache eficiente)
COPY pyproject.toml uv.lock ./

# Instala dependências (sem dev)
RUN uv sync --frozen --no-dev

# Copia o resto do código
COPY . .

# Porta padrão do FastAPI
EXPOSE 8000

# Rodar com uv
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]