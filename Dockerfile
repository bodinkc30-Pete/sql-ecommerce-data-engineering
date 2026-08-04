FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1

WORKDIR /app

COPY requirements.txt .

RUN pip install \
    --no-cache-dir \
    --requirement requirements.txt

RUN addgroup --system appgroup \
    && adduser \
    --system \
    --ingroup appgroup \
    appuser

COPY --chown=appuser:appgroup config/ ./config/
COPY --chown=appuser:appgroup data/raw/synthetic/ ./data/raw/synthetic/
COPY --chown=appuser:appgroup schema/ ./schema/
COPY --chown=appuser:appgroup transformations/ ./transformations/
COPY --chown=appuser:appgroup quality_checks/ ./quality_checks/
COPY --chown=appuser:appgroup queries/ ./queries/
COPY --chown=appuser:appgroup scripts/ ./scripts/
COPY --chown=appuser:appgroup tests/ ./tests/

RUN mkdir -p \
    database \
    logs \
    data/staging \
    data/processed \
    && chown -R appuser:appgroup /app

USER appuser

CMD ["python", "scripts/05_run_pipeline.py"]