# Combined Dockerfile with two build targets: dashboard and collector


# Base image
FROM python:3.11-slim AS base
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Dashboard target
FROM base AS dashboard
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]


# Collector target
FROM base AS collector
WORKDIR /collector
COPY collector.py ./
CMD ["python", "collector.py"]