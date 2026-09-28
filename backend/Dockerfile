# One image for both backend processes. docker-compose.yml runs it twice:
#   api    -> uvicorn app.main:app          (FastAPI + Temporal Client)
#   worker -> python -m app.temporal_worker (Temporal Worker: workflow + activities)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# Default command = API. The worker service overrides this in docker-compose.yml.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
