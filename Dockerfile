FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --user-group --uid 10001 appuser

COPY scripts/fetch_models.py ./scripts/fetch_models.py
RUN python scripts/fetch_models.py --output /app/models

COPY app ./app
COPY static ./static
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY THIRD_PARTY_NOTICES.md ./THIRD_PARTY_NOTICES.md

USER 10001:10001
EXPOSE 8000
CMD ["sh", "-c", "if [ \"${RUN_MIGRATIONS_ON_START:-true}\" = \"true\" ]; then alembic upgrade head; fi && python -m app.bootstrap_env && unset INITIAL_ADMIN_PASSWORD INITIAL_ADMIN_EMAIL && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --no-access-log"]
