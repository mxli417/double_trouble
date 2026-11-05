# Gallery MLOps

The reference gallery is a versioned ML artifact, not application seed data. It is built outside the web service, contains labels, provenance, model metadata, and face vectors, and is ingested into PostgreSQL with deterministic, repeatable upserts. Source photos are never shipped in the artifact or served by Double Trouble.

## Rights gate

LFW is useful as a small, labeled research baseline, but its image rights are not clear enough for this repository to redistribute the photos or claim blanket public-use permission. Download and vectorization require an explicit operator acknowledgement. Review the intended jurisdiction and use before proceeding; keeping only derived vectors does not remove the need for that review.

Do not commit source photos, generated bundles, database URLs, or credentials.

## Build a vector-only bundle

Use the same pinned YuNet/SFace artifacts and model label as the target application:

```sh
python scripts/fetch_models.py --output models
python scripts/fetch_lfw.py --destination data --acknowledge-unclear-lfw-rights
FACE_MODEL_PATH=models python -m app.gallery build \
  --lfw-dir data/lfw_funneled \
  --output artifacts/lfw-sface.jsonl.gz \
  --acknowledge-lfw-rights-review
```

The compressed JSONL artifact records identity labels, deterministic source IDs, provenance, embedding dimension, model version, and 128-dimensional vectors. It contains no image bytes.

Treat the bundle as immutable. Name or catalog it with its dataset snapshot, model version, build code revision, and checksum. A rebuilt artifact with different inputs is a new release even if the filename would otherwise be the same.

## Load a local gallery

With the development stack running:

```sh
docker compose -f compose.dev.yaml exec app \
  python -m app.gallery ingest --bundle /app/artifacts/lfw-sface.jsonl.gz
```

`compose.dev.yaml` mounts the ignored host directory `artifacts/` read-only at
`/app/artifacts`. This preserves the read-only container root filesystem; `docker compose cp`
cannot copy into this hardened container and is intentionally not part of the workflow.

Ingestion rejects a bundle whose vector dimension or model version differs from the application configuration. Repeating the same ingest is safe because source IDs drive idempotent upserts.

## Load a Render gallery

Render Free provides no application shell or pre-deploy job, so ingestion is an operator action from a trusted workstation or controlled CI runner:

1. Allow only the runner's current public IP on the target Render PostgreSQL external connection.
2. Use the external TLS connection URL with the same application code and dependencies as the target release.
3. Run the ingest command against the reviewed bundle.
4. Verify gallery state and representative queries.
5. Remove external database access immediately.

```sh
DATABASE_URL='postgresql+psycopg://...' \
FACE_MODEL_VERSION='yunet-2023mar+sface-2021dec' \
FACE_EMBEDDING_DIM=128 \
python -m app.gallery ingest --bundle artifacts/lfw-sface.jsonl.gz
```

Never paste the database URL into logs, shell history shared with others, tickets, or CI output.

## Quality and release gates

Before promoting a gallery/model pair:

- verify artifact checksum, record count, provenance completeness, dimension, and model label;
- measure detection failures and identity coverage;
- evaluate nearest-neighbor quality on a held-out, rights-cleared set;
- calibrate the self-similarity threshold with same-person/different-lighting and different-person pairs;
- record false-accept and false-reject rates by provider version;
- benchmark search latency, total request latency, memory, and cold-start behavior on staging;
- confirm the API returns unique identities and never source photos or bulk vectors.

Exact cosine search is the baseline at LFW scale. Add an HNSW index only after measurements show that approximate retrieval is needed, and capture its recall/latency trade-off in a new ADR.

## Updating the model or dataset

A new detector, encoder, embedding dimension, or material dataset change produces a new gallery version. Build it side by side, validate it on staging, recalibrate thresholds, and coordinate its activation with the matching application version. Do not silently mix embeddings produced by different encoders under one model label.

See [ADR 0002](adr/0002-embedding-and-gallery.md) for retrieval/privacy decisions and [ADR 0008](adr/0008-cpu-vision-and-gallery-delivery.md) for artifact delivery and licensing constraints.
