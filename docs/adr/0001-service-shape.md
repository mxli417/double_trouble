# ADR 0001: Single same-origin web service

- Status: Accepted for MVP
- Date: 2026-11-01

## Context

The app needs a playful browser UI, an upload endpoint, vector search, Elo voting, and a deployable public demo. Splitting frontend and API adds CORS and another service without helping the first release.

## Decision

Serve static HTML/CSS/JS and a FastAPI API from one Docker web service on Render. Use Render Postgres in the same region and connect over the private network.

## Consequences

- Same-origin requests avoid CORS configuration.
- One service can be deployed after CI checks pass.
- Scale the API and database independently later if measurements require it.
- Model memory and CPU latency must be benchmarked before enabling public matching.
