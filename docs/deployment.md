# Deployment blueprint

Double Trouble is deployed as one same-origin Docker web service plus PostgreSQL/pgvector. The container serves the static UI and FastAPI API, loads checksum-pinned CPU model artifacts and a digest-pinned private gallery artifact, applies Alembic migrations and idempotent gallery ingestion at startup, and exposes `/api/health` plus strict `/api/ready`. It does not require Render SSH, a pre-deploy command, a writable model cache, or a persistent web-service disk.

## Environment topology

| Environment | Git branch | Purpose |
| --- | --- | --- |
| Development | `dev` | Integrated feature work and synthetic checks. |
| Staging | `staging` | Release candidate, gallery compatibility, latency, memory, and migration checks. |
| Production | `main` | Reviewed releases only. |

Use a separate Render web service and database for each environment. Connect production only to `main`; never share databases or secrets across environments. `compose.dev.yaml` and `compose.staging.yaml` mirror the service shape locally but do not replace managed TLS, secrets, backups, or branch protection.

## Render setup

1. Push the repository, including `render.yaml`, to GitHub.
2. In Render choose **New → Blueprint**, connect the repository, select `main`, and keep the default Blueprint path `render.yaml`. The production service is also pinned to `branch: main` in the Blueprint.
3. In Render Workspace Settings, add a private GHCR registry credential named `double-trouble-ghcr`. Use the GitHub account name and a token with `read:packages`; grant the package read access to the repository.
4. Review the proposed web service and PostgreSQL database, provide every `sync: false` secret, and deploy the Blueprint.
5. Keep service deploys gated on successful GitHub checks (`autoDeployTrigger: checksPass`).
6. Confirm `/api/health` reports the expected environment and `/api/ready` returns `200` with loaded gallery, Hot or Not, and face models ready.

The application should receive at least:

- Core: `DATABASE_URL`, `ALLOWED_HOSTS`, `DEPLOYMENT_ENVIRONMENT`, `LOG_LEVEL`.
- Vision: `MATCHING_ENABLED`, `FACE_PROVIDER`, `FACE_MODEL_PATH`, `FACE_MODEL_VERSION`, `FACE_EMBEDDING_DIM`, `SELF_SIMILARITY_THRESHOLD`, `GALLERY_REQUIRED`, `GALLERY_BUNDLE_PATH`, `GALLERY_BUNDLE_SHA256`.
- Auth: `SESSION_COOKIE_SECURE=true`, `SESSION_HOURS`, `INVITE_HOURS`, and one of the bootstrap methods below.
- Consent storage: `CONSENTED_STORAGE_ENABLED`, `DATA_ENCRYPTION_KEY`, `DATA_ENCRYPTION_KEY_VERSION`, `RETAINED_UPLOAD_DAYS`, `RETAINED_IMAGE_MAX_SIDE`, `CONSENT_TEXT_VERSION`.
- Optional narration: `MATCH_NARRATION_ENABLED`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TIMEOUT_SECONDS`.
- Experiments: `EXPERIMENT_VARIANT`, assigned by the platform rather than from identity or biometric data.

`.env.example`, `.env.staging.example`, and `render.yaml` are the executable configuration references. A missing encryption key or OpenAI key makes the corresponding optional feature unavailable; it must not weaken the default request-only path.

## First administrator

The simplest automated bootstrap sets `INITIAL_ADMIN_EMAIL` and a unique `INITIAL_ADMIN_PASSWORD` for the first deployment. Startup creates an administrator only when none exists. Remove both values from Render and redeploy immediately afterward.

Alternatively, set a random `BOOTSTRAP_SECRET`, deploy, and complete `/setup-admin` once. The database records that setup as consumed. Remove the secret afterward. In both cases, create a second trusted administrator as a recovery path; normal account creation and password resets then use invite links from `/admin`.

## Promotion flow

```text
feature branch -> pull request -> dev -> staging -> main
```

- Merge feature branches into protected `dev` after CI.
- Promote `dev` to `staging`; do not bypass the release-candidate environment.
- Verify migrations, login, invitations, the optional two-photo self-check, pictured representative matches, consented Hot or Not participation/voting/withdrawal, logs, CPU latency, memory, and `/api/health` on staging.
- Promote the reviewed staging commit to `main`. Do not merge `dev` directly to `main`.
- Require the same CI status on all three protected branches and prohibit force-pushes and branch deletion.

GitHub Actions runs Ruff, Python compilation, unit tests, Compose validation, and a production Docker build. Database changes must remain backward-compatible across a rolling deployment. Use expand/migrate/contract over multiple promotions for destructive changes.

## Recommended CLI and automation

Use GitHub CLI for pull requests and promotion, and let Render's native Git integration perform routine deploys after required checks pass:

```sh
gh auth login
gh pr create --base dev --fill
gh pr checks --watch
gh pr merge --squash --auto

gh pr create --base staging --head dev --fill
gh pr create --base main --head staging --fill
```

Protect `dev`, `staging`, and `main` with GitHub rulesets that require pull requests, the `static-checks` job, resolved conversations, and no force-pushes or deletions. Avoid `--admin` merges that bypass those gates.

The official Render CLI is useful for validation, inspection, and intentional manual redeploys. On Windows:

```powershell
winget install render.cli
render login
render blueprints validate render.yaml
render services
render deploys list <service-id>
render deploys create <service-id> --commit <git-sha> --wait
render psql <database-id>
```

Do not add a second GitHub Actions deploy trigger while `autoDeployTrigger: checksPass` is active; that would create duplicate deploys and require an unnecessary Render API key in GitHub. If native auto-deploy is deliberately disabled later, use a separately approved deployment workflow with GitHub Environment protection, a pinned Render CLI release, `RENDER_API_KEY`, and the environment-specific service ID.

## Gallery and model release

The web service never downloads LFW or builds the gallery during startup. Model artifacts are checksum-pinned in the image; the separately reviewed gallery is supplied by a private OCI build stage pinned by registry digest and checked for bundle checksum, model version, and dimension during ingestion. A model or gallery change therefore requires:

1. a new model-version label and pinned image build;
2. a rebuilt vector gallery;
3. quality, threshold, latency, and memory evaluation on staging;
4. publishing the new private gallery image and pinning its digest and bundle checksum;
5. coordinated application and gallery promotion.

## Observability and experiments

Request logs are structured and correlated with W3C trace/request IDs. They exclude bodies, query strings, photos, embeddings, similarity scores, tokens, account identifiers, and IP addresses. Render readiness checks use `/api/ready`; the lightweight `/api/health` remains available for diagnostics, and matching still returns `503` when disabled or incompletely configured.

`EXPERIMENT_VARIANT` supports later platform-level A/B routing. Keep variant assignment outside the application, expose it as environment/request metadata, and never derive a cohort from a face, account identity, or other sensitive trait.

## Operational gates

- Keep PostgreSQL private; startup ingestion uses the internal database connection and needs no external allow-list.
- Back up the managed database and retain the encryption key according to the retention policy; losing it makes consented records unreadable.
- Measure cold starts, memory, and inference latency before sizing the production service.
- Use a durable database and appropriately sized web instance for a real launch.
- Add scheduled cleanup if expiry must be enforced while the application receives no traffic; the current request-driven sweep only runs during API activity.
