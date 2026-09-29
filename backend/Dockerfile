FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/app/data \
    LOG_DIR=/app/logs \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home /app app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

RUN mkdir -p /app/data /app/logs && chown -R app:app /app/data /app/logs
USER app

VOLUME ["/app/data", "/app/logs"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"APP_PORT\",\"8000\")}/ready', timeout=4).status == 200 else 1)"

# Host, port, reload and log level all come from the environment (see .env.example).
# Keep one process per container so the in-process scheduler and rate limiter stay single-instance.
CMD ["python", "-m", "app"]
