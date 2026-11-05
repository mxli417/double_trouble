# ADR 0007: Platform experiments and privacy-safe observability

- Status: Accepted for staged rollout
- Date: 2026-11-05

## Context

Dev, staging, and production need comparable diagnostics without logging biometric input. Later product experiments must not introduce in-process random assignment, variant drift, or hidden coupling to matching logic.

## Decision

- Emit one-line JSON logs to stdout for the platform log stream. Include timestamp, severity, route template, status, duration, deployment environment, experiment variant, generated request ID, and W3C trace ID. Never log query strings, request/response bodies, IP addresses, account IDs, tokens, photos, embeddings, image metadata, or similarity scores.
- Accept a valid incoming `traceparent` and generate a new span ID; otherwise create a new trace. Return `traceparent` and `X-Request-ID` for correlation. This is propagation and correlation, not a full exporter; add an OpenTelemetry exporter only when an approved collector and retention policy exist.
- Set `DEPLOYMENT_ENVIRONMENT` and `EXPERIMENT_VARIANT` per deployment. Return the variant in `X-Experiment-Variant` and `/api/health`, and include it in logs. Application code does not randomly assign users.
- For a future A/B test, deploy the same immutable image as separate platform services with different `EXPERIMENT_VARIANT` and variant-specific configuration. An upstream edge/router performs weighted, sticky assignment. Use an opaque, non-identifying assignment cookie if stickiness is required; do not derive assignment from an email, account ID, face, or IP address.
- Compare aggregate route/status/latency and separately approved product metrics by variant. Matching quality thresholds, model/provider changes, and gallery contents are safety-sensitive changes and must first pass offline evaluation and staging; they are not ordinary UI experiments.

## Consequences

- Current Render configuration represents the control production service. Additional variant services and weighted routing are intentionally not provisioned until an edge layer, rollback rule, sample-size plan, and privacy/retention review are chosen.
- Correlation works across proxies that preserve W3C headers. Full spans and database instrumentation remain a later operational choice rather than silently exporting telemetry.
- Variant services must use schema-compatible releases. Database changes follow expand/migrate/contract, and rollback must not depend on reversing a destructive migration.
