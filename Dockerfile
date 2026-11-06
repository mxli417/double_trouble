ARG GALLERY_IMAGE=ghcr.io/mxli417/double-trouble-gallery@sha256:51376155fec2299a91e77d3a076f5e50b7384d18c0aecc92e1c8c7031dd5487c
FROM ${GALLERY_IMAGE} AS gallery

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
COPY --from=gallery /gallery/lfw-sface.jsonl.gz /app/gallery/lfw-sface.jsonl.gz

USER 10001:10001
EXPOSE 8000
CMD ["sh", "-c", "if [ \"${RUN_MIGRATIONS_ON_START:-true}\" = \"true\" ]; then alembic upgrade head; fi && python -m app.bootstrap_runtime && unset INITIAL_ADMIN_PASSWORD INITIAL_ADMIN_EMAIL && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --no-access-log"]
