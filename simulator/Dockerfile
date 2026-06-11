FROM python:3.12-slim
WORKDIR /app
COPY simulator.py /app/
RUN pip install --no-cache-dir aiohttp
ENTRYPOINT ["python", "simulator.py"]
