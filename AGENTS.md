# Repository working agreement

## Map of the application

- `app.main:app` is the production and local FastAPI entry point. It serves the same-origin UI from `static/` and the API; the main pages are `/`, `/accept`, `/setup-admin`, and `/admin`.
- The vision path is `/api/self-similarity` and `/api/match` through `app/images.py`, the interface in `app/face_provider.py`, the YuNet/SFace implementation in `app/opencv_provider.py`, and the pgvector query in `app/main.py`. Model acquisition is checksum-pinned in `scripts/fetch_models.py`.
- Gallery build and idempotent ingest use `python -m app.gallery`; follow `docs/gallery-mlops.md` and ADRs 0002/0008. Face Off uses `/api/duel`, `/api/duel/{id}/vote`, and `app/elo.py`.
- Auth, sessions, invitations, roles, audit events, and first-admin setup live in `app/auth.py`, `app/bootstrap_admin.py`, `app/bootstrap_env.py`, and the auth/admin handlers in `app/main.py`. Optional narration is isolated in `app/narration.py`.
- Configuration is centralized in `app/config.py`. SQLAlchemy models are in `app/models.py`; Alembic uses `alembic.ini`, `migrations/env.py`, and `migrations/versions/`.

## Work and verification

- Check `git status` first and preserve unrelated local changes. Do not deploy, ingest remote data, rotate secrets, or mutate external services unless the user explicitly asks.
- Prefer the Render-shaped local path: `docker compose -f compose.dev.yaml up --build`. Direct host startup uses Python 3.12: run `uv sync --locked`, configure `.env`, fetch the pinned models, run `uv run alembic upgrade head`, then `uv run uvicorn app.main:app --reload`.
- Treat `pyproject.toml` and `uv.lock` as dependency sources; `requirements.txt` is the exported runtime input for the container. Mirror `.github/workflows/ci.yml`: lock validation, pre-commit config validation, Ruff, Bandit, Python compilation, unit tests, both Compose validations, and a Docker build. For schema changes also run `alembic upgrade head` and `alembic check` against PostgreSQL.
- Exercise changes through `app.main:app`. Check `/api/health`, authentication, and the documented matching `503` path; use synthetic or rights-cleared images. Report exactly which checks ran and which could not run.

## Invariants

- Preserve the same-origin service, face-provider boundary, PostgreSQL/pgvector data layer, and startup migrations. Render must not depend on SSH, a pre-deploy command, dataset downloads, or a writable runtime model cache; see `docs/deployment.md` and ADRs 0001/0005.
- Preserve invite-only registration, Argon2id passwords, opaque database-hashed session/invitation tokens, per-request role checks, session revocation, the one-time admin bootstrap, and audited admin access; see ADRs 0006/0009.
- Photos and query embeddings are request-only by default. Retain only the first normalized photo and its vector after explicit per-match opt-in, encrypt both at application level, record consent/version/expiry, support withdrawal, and keep admin reads role-gated and audited. Never retain the second self-check photo.
- Never log request bodies, query strings, IP/account identifiers, tokens, photos, embeddings, image metadata, or similarity scores. Preserve structured logs, W3C trace/request correlation, and platform-provided experiment labels. Never derive A/B cohorts from identity or biometric data.
- Matching defaults to disabled and remains fail-closed with `503` when disabled, models are unavailable, configuration is incompatible, or the gallery is empty. Never automatically download LFW, other face photos, or unpinned model weights.
- Keep model/version/dimension checks across image, gallery, and deployment changes. Treat similarity as relative retrieval, self-similarity as a quality check, and Elo as subjective entertainment—not identity proof or an objective attractiveness score.
- Keep diffs focused and update the relevant README, operational guide, data-model document, or ADR when behavior or durable decisions change.
