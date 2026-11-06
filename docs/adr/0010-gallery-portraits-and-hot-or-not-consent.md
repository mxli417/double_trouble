# ADR 0010: Gallery portraits and consented Hot or Not participation

- Status: Accepted for the private PoC; reference-image rights review required
- Date: 2026-11-06

## Context

Names alone do not provide the intended party experience. Match results should place the request-local upload beside the pictured reference matches, and invited users should be able to contribute a portrait to the preference game. Reference-image rights and guest biometric consent are different concerns and must not be conflated.

## Decision

- A gallery artifact may contain one normalized JPEG portrait per identity in addition to all face vectors. Building such an artifact requires both the existing LFW acknowledgement and the explicit `--include-portraits` flag. Vector-only bundles remain supported and produce matches without portraits.
- Ingestion stores the single gallery portrait on the candidate row and activates that identity for Hot or Not. Portrait bytes are returned only through an authenticated, no-store endpoint. The API returns individual URLs, never inline bytes or bulk exports.
- Displaying LFW portraits remains a launch gate: noncommercial PoC intent does not create redistribution rights. Production must use a source with documented display rights or keep portrait ingestion disabled.
- A guest joins Hot or Not only when the same request contains processing consent, encrypted-retention consent, a separate Hot or Not consent, and a 2-40 character nickname that is not an email address. The encrypted upload is the source of the displayed portrait. The vector is never exposed.
- One active guest candidate exists per account. A new consented portrait replaces its linked upload while preserving rating history. Expiry, owner withdrawal, or admin deletion unlinks and deactivates the candidate, replaces its nickname, and removes it from all serving queries while preserving immutable historical vote events. A voter does not receive a matchup containing their own guest candidate.
- The browser shows its own upload from a local object URL; it does not need the server to echo the uploaded bytes. Interactive notifications announce success, warnings, and errors without replacing inline accessible status regions.
- The two-photo self-similarity check is an optional sidebar tool. It remains request-only and no longer gates the ordinary match request.

## Consequences

Portrait-enabled bundles and PostgreSQL storage are materially larger than vector-only operation and must be measured on the chosen Render plan. Gallery changes require a fresh bundle and idempotent ingest after migration. Guest participation consumes encrypted database storage and requires a clear notice, short retention, withdrawal, abuse reporting before wider use, and jurisdiction-specific biometric/privacy review.
