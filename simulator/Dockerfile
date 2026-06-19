# FROM python:3.12-slim
# ENV PYTHONUNBUFFERED=1
# WORKDIR /app
# COPY simulator.py /app/
# RUN pip install --no-cache-dir aiohttp
# ENTRYPOINT ["python", "simulator.py"]

FROM grafana/k6:latest
USER root
WORKDIR /app
COPY k6-script.js /app/
COPY entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
