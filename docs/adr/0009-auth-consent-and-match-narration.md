# ADR 0009: Auth primitives, biometric consent, and optional narration

- Status: Accepted for the private PoC; legal and retention review required before wider launch
- Date: 2026-11-05

## Decision

- Keep `pwdlib` Argon2id password hashes. Werkzeug's current scrypt helper is sound but would add a second password-hash format without improving this application. Do not use itsdangerous for passwords. Keep opaque, random, database-hashed session and invitation tokens because they are individually revocable and disclose no payload.
- Processing consent is required for each match. Biometric retention, Hot or Not participation, and OpenAI narration are separate, unchecked choices. Hot or Not requires retention but retention does not imply participation. A retained record stores consent version/time, a normalized JPEG and its SFace vector encrypted separately, model version, owner, and expiry. A participating record also stores the game-consent version/time and links to one pseudonymous rating candidate. Self-check photos are never retained.
- `DATA_ENCRYPTION_KEY` is a Render secret and is never stored in PostgreSQL. A key version is stored with every record; rotate only after deleting or re-encrypting records created with the old key.
- Admin image/vector reads and deletions are role-gated and audited. The owner can delete all retained uploads; this unlinks, anonymizes, and deactivates their Hot or Not candidate while preserving vote history. Expiry cleanup does the same. Signed-in players can view only the decrypted portrait of an actively consented candidate, never its vector or owner identity.
- Narration uses the server-side OpenAI Responses API with `store=false`. It sends only public candidate names and rounded scores, never a user photo, face vector, email, account ID, or session data. Matching succeeds even if narration fails.

## Consequences

Render needs no shell: Alembic runs at startup and all secrets are environment variables. PostgreSQL is intentionally used instead of Render disk so records survive web-service replacement, but retained images consume managed-database capacity. The default 30-day period and 1024-pixel retained image bound require review for the chosen plan and jurisdiction.
