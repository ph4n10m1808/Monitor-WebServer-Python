# Dockerfile với multi-stage build
FROM python:3.11-slim AS base

WORKDIR /app

# Copy requirements và install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Dashboard service
FROM base AS dashboard
COPY src/app.py .
COPY src/templates ./templates
COPY src/static ./static
EXPOSE 5000
ENV MONGO_HOST=mongodb
ENV MONGO_PORT=27017
ENV MONGO_DB=logdb
ENV MONGO_COLLECTION=logs
CMD ["python", "app.py"]

# Collector service
FROM base AS collector
COPY src/collector.py .
ENV MONGO_HOST=mongodb
ENV MONGO_PORT=27017
ENV MONGO_DB=logdb
ENV MONGO_COLLECTION=logs
ENV LOG_PATH=/logs/access.log
CMD ["python", "collector.py"]
