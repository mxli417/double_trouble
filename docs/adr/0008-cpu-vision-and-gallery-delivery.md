# ADR 0008: CPU vision artifacts and gallery delivery

- Status: Accepted for the private noncommercial PoC
- Date: 2026-11-05

## Decision

- Build the Render image with checksum-pinned YuNet and SFace ONNX artifacts. Run OpenCV on CPU; do not depend on CUDA or a writable runtime model cache.
- Do not use Ultralytics YOLO: its standard code and trained models are AGPL-3.0, which does not meet this project's permissive-license constraint. A future detector must be face-trained, CPU-benchmarked, and have independently verified code and weight licenses.
- Keep LFW acquisition and vectorization outside application startup. Both commands require explicit rights acknowledgement. The generated gzip JSONL artifact always contains labels, provenance, model metadata, and vectors. Under ADR 0010 it contains one display portrait per identity only when the operator additionally selects `--include-portraits` after reviewing display rights.
- Publish the reviewed bundle as a private, immutable OCI image. The application Dockerfile references that image by registry digest, copies the bundle into the final read-only image, and verifies the bundle's independent SHA-256 checksum before ingestion. Never place database credentials or the bundle in Git.
- Run ingestion after startup migrations and before Uvicorn. Serialize concurrent starts with a PostgreSQL advisory lock, stream bounded batches, and record the loaded bundle digest so unchanged releases are skipped on restarts. Reject bundles whose checksum, embedding dimension, or model version differs from the running service.
- Configure Render with a read-only GHCR registry credential. Do not download LFW or any mutable dataset during the Render build or application startup.

## Consequences

The web service remains independently deployable and needs no SSH, pre-deploy job, dataset download, external database allow-list, or persistent disk. The private OCI artifact becomes a build dependency and must remain available to Render. Model or gallery updates require a new immutable artifact digest, staging quality evaluation, and a coordinated rollout. LFW's unclear redistribution terms remain an operator launch gate; portrait display is a stricter gate than vector-only retrieval and must be disabled when rights are unresolved.
