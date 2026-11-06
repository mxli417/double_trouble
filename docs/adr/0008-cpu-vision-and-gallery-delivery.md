# ADR 0008: CPU vision artifacts and gallery delivery

- Status: Accepted for the private noncommercial PoC
- Date: 2026-11-05

## Decision

- Build the Render image with checksum-pinned YuNet and SFace ONNX artifacts. Run OpenCV on CPU; do not depend on CUDA or a writable runtime model cache.
- Do not use Ultralytics YOLO: its standard code and trained models are AGPL-3.0, which does not meet this project's permissive-license constraint. A future detector must be face-trained, CPU-benchmarked, and have independently verified code and weight licenses.
- Keep LFW acquisition and vectorization outside application startup. Both commands require explicit rights acknowledgement. The generated gzip JSONL artifact always contains labels, provenance, model metadata, and vectors. Under ADR 0010 it contains one display portrait per identity only when the operator additionally selects `--include-portraits` after reviewing display rights.
- Load the bundle from a trusted workstation or CI environment with `python -m app.gallery ingest` over Render PostgreSQL's external TLS URL. Temporarily allow only the operator's source IP, then close external access. Never place database credentials or the bundle in Git.
- Reject bundles whose embedding dimension or model version differs from the running service. Use deterministic source IDs and idempotent upserts so ingestion is safely repeatable.

## Consequences

The web service remains independently deployable and needs no SSH, pre-deploy job, dataset download, or persistent disk. Model updates require a new model-version label, rebuilt gallery, staging quality evaluation, and a coordinated rollout. LFW's unclear redistribution terms remain an operator launch gate; portrait display is a stricter gate than vector-only retrieval and must be disabled when rights are unresolved.
