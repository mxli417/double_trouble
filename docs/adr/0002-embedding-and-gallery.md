# ADR 0002: Face embeddings, pgvector, and a gated reference index

- Status: Accepted, amended by ADR 0010 for portrait presentation
- Date: 2026-11-01

## Context

The app compares one visitor query with a named reference set and returns the nearest celebrity identities. Generic image embeddings can over-weight hair, clothing, backgrounds, and lighting. Face-specific embeddings are a better candidate, but code, weights, training data, and source images can have separate licenses.

## Decision

- The API uses an operator-controlled provider interface for face detection, alignment, and normalized face embeddings. The CPU provider uses OpenCV YuNet 2023mar (MIT) for detection and five landmarks, followed by OpenCV SFace 2021dec (Apache-2.0) for alignment and a 128-dimensional unit vector.
- Use LFW as a gated reference index: precompute one vector per face sample; store the vector, identity, source dataset, source image ID, source URL if available, and license/provenance metadata. ADR 0010 permits one display portrait per identity only after an additional explicit portrait-rights review.
- Store multiple face samples per identity. For matching, take the nearest sample distance per identity, then return the top unique identities, an optional Wikipedia article URL, and an authenticated portrait URL when a cleared portrait was ingested. Never provide bulk image or vector exports.
- LFW ingestion is an explicit, gated noncommercial-PoC operation. The upstream distribution does not provide a sufficiently clear image license for this project to assert redistribution rights. Operators must review provenance and rights before downloading or deriving vectors. User-facing 1:N lookalike quality needs separate evaluation using rights-cleared human judgments.
- Stream the visitor image as a size-bounded HTTPS request body, embed it in process memory, and run the nearest-neighbor query. Discard it by default; ADR 0009 permits retention only after explicit per-match consent, with encryption, expiry, withdrawal, and audited access. Never put biometric input in logs or analytics.
- Offer a separate, optional self-similarity tool for two photos of the same visitor taken under different lighting. Compute cosine similarity between the two request-local embeddings and return only the score, threshold, and pass/fail result; never persist either image or embedding. A weak result is a calibration/quality warning, not an identity decision and does not block gallery matching.

## Implementation

- YuNet selects a clear face using confidence, size, and center proximity. SFace aligns the selected face from five landmarks and produces the normalized vector. Generic COCO YOLO weights are unsuitable because they do not have a face class. Ultralytics code and weights are AGPL-3.0 by default, so no Ultralytics YOLO generation is used under the permissive-license requirement. The provider boundary allows a later, independently licensed face-specific detector.
- The application validates the vector and uses exact pgvector cosine distance (`<=>`), takes the nearest stored sample per identity, and returns five unique identities. It performs similarity ranking, not identity verification or classifier-based recognition.
- Multiple LFW samples per identity are retained as vectors with provenance so lighting/pose variation is represented without serving the source photos. HNSW remains deferred until exact-search latency demonstrates a need.
- `scripts/fetch_models.py` pins model URLs and SHA-256 hashes. `scripts/fetch_lfw.py` requires an explicit rights acknowledgement. `python -m app.gallery build` creates a compressed bundle and includes one portrait per identity only with `--include-portraits`; `python -m app.gallery ingest` performs idempotent PostgreSQL upserts.

## Launch gates

- Confirm the intended legal basis for creating and retaining the gated LFW-derived index. Serving portraits is a separate launch gate under ADR 0010 and must remain disabled unless that review succeeds.
- Benchmark memory, latency, detection failures, and SFace thresholds on the selected Render plan.
- Review data-protection obligations for named reference embeddings and visitor queries. A non-persistent query still involves processing.
- Compare retrieval quality with a held-out evaluation set; present cosine similarity as relative ranking, not identity certainty.
- Calibrate the self-similarity threshold with synthetic or legally cleared same-person/different-lighting pairs and a separate different-person set. Record false-accept and false-reject rates by provider/model version before enabling matching.

## Consequences

Application configuration remains fail-closed by default. A deployment may enable matching once the pinned provider is present, but an empty/mismatched gallery still produces `503`. For LFW-scale data, exact cosine search is the baseline; add HNSW only if measured latency warrants approximate retrieval.
