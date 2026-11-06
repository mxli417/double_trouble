# Gallery MLOps

The reference gallery is a versioned ML artifact, not application seed data. It is built outside the web service, contains labels, provenance, model metadata, and face vectors, and is ingested into PostgreSQL with deterministic, repeatable upserts. A portrait-enabled release may additionally contain one normalized display JPEG per identity after a separate rights review.

## Rights gate

LFW is useful as a small, labeled research baseline, but its image rights are not clear enough for this repository to redistribute or publicly display the photos or claim blanket public-use permission. Download and vectorization require an explicit operator acknowledgement. Displaying portraits is an additional launch gate. Review the intended jurisdiction and use before proceeding; neither noncommercial intent nor keeping only derived vectors removes that obligation.

Do not commit source photos, generated bundles, database URLs, or credentials.

## Build a portrait-enabled bundle

Use the same pinned YuNet/SFace artifacts and model label as the target application:

```sh
python scripts/fetch_models.py --output models
python scripts/fetch_lfw.py --destination data --acknowledge-unclear-lfw-rights
FACE_MODEL_PATH=models python -m app.gallery build \
  --lfw-dir data/lfw_funneled \
  --output artifacts/lfw-sface.jsonl.gz \
  --include-portraits \
  --acknowledge-lfw-rights-review
```

The compressed JSONL artifact records identity labels, deterministic source IDs, provenance, embedding dimension, model version, 128-dimensional vectors, and one normalized JPEG per identity. Omit `--include-portraits` to build a vector-only artifact; matching still works, but result cards have no gallery images and those identities do not enter Hot or Not.

Treat the bundle as restricted and immutable. Name or catalog it with its dataset snapshot, portrait mode, model version, build code revision, and checksum. Do not commit it or expose it as a public download. A rebuilt artifact with different inputs is a new release even if the filename would otherwise be the same.

## Load a local gallery

With the development stack running:

```sh
docker compose -f compose.dev.yaml exec app \
  python -m app.gallery ingest --bundle /app/artifacts/lfw-sface.jsonl.gz
```

`compose.dev.yaml` mounts the ignored host directory `artifacts/` read-only at
`/app/artifacts`. This preserves the read-only container root filesystem; `docker compose cp`
cannot copy into this hardened container and is intentionally not part of the workflow.

Ingestion rejects a bundle whose vector dimension or model version differs from the application configuration. Repeating the same ingest is safe because source IDs drive idempotent upserts. Portrait-enabled ingestion sets `is_hot_or_not_active` for pictured identities; a vector-only ingest does not erase portraits already reviewed and loaded.

## Publish and load a Render gallery

The reviewed local bundle is published as a private OCI image; it is never committed or exposed as a public download. Build from the ignored `artifacts/` directory and use an immutable release tag:

```sh
docker login ghcr.io
docker buildx build --platform linux/amd64 \
  -f deploy/gallery.Dockerfile \
  -t ghcr.io/mxli417/double-trouble-gallery:lfw-sface-2021dec-70b441d5 \
  --push artifacts
docker buildx imagetools inspect \
  ghcr.io/mxli417/double-trouble-gallery:lfw-sface-2021dec-70b441d5
```

Keep the package private. Configure a Render registry credential named `double-trouble-ghcr` with a GitHub token limited to `read:packages`, and grant the application repository read access to the package. Pin the resulting registry digest in `Dockerfile` and the independent bundle SHA-256 in `render.yaml`.

At startup the application applies migrations, verifies the bundle checksum and manifest, obtains a PostgreSQL advisory lock, and ingests bounded batches over the internal connection. A `gallery_releases` row records the digest, so subsequent restarts skip unchanged data. Any verification or ingestion error prevents Uvicorn from starting; `/api/ready` remains fail-closed until the gallery, Hot or Not portraits, and face provider are ready.

## Quality and release gates

Before promoting a gallery/model pair:

- verify artifact checksum, record count, provenance completeness, dimension, and model label;
- measure detection failures and identity coverage;
- evaluate nearest-neighbor quality on a held-out, rights-cleared set;
- calibrate the self-similarity threshold with same-person/different-lighting and different-person pairs;
- record false-accept and false-reject rates by provider version;
- benchmark search latency, total request latency, memory, and cold-start behavior on staging;
- confirm the API returns unique identities, authenticates every individual portrait request, applies `no-store`, and never offers bulk photos or vectors;
- verify that the source terms permit the intended portrait display before enabling Hot or Not for gallery identities.

Exact cosine search is the baseline at LFW scale. Add an HNSW index only after measurements show that approximate retrieval is needed, and capture its recall/latency trade-off in a new ADR.

## Updating the model or dataset

A new detector, encoder, embedding dimension, or material dataset change produces a new gallery version. Build it side by side, validate it on staging, recalibrate thresholds, and coordinate its activation with the matching application version. Do not silently mix embeddings produced by different encoders under one model label.

See [ADR 0002](adr/0002-embedding-and-gallery.md) for retrieval decisions, [ADR 0008](adr/0008-cpu-vision-and-gallery-delivery.md) for artifact delivery, and [ADR 0010](adr/0010-gallery-portraits-and-hot-or-not-consent.md) for portrait and guest-consent constraints.
