FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HELP_DIR=/app/help

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# The help/ KB is mounted at runtime (see docker-compose.yml) so edits don't need a rebuild.
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
