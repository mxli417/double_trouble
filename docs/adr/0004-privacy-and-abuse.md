# ADR 0004: Privacy and abuse controls

- Status: Accepted for MVP; production review required
- Date: 2026-11-01

## Decision

- Accept JPEG, PNG, WebP, HEIC, and HEIF; cap each upload at 10 MiB and 40 megapixels, apply EXIF orientation, convert to RGB, and downscale to a 1600-pixel maximum side in request memory. Discard source and normalized bytes after the request.
- The self-similarity check accepts exactly two bounded images in one authenticated request. Both image byte strings and both query embeddings exist only in process memory for that request. Store or log neither; return only a rounded similarity, the configured threshold, and pass/fail.
- By default, the match image and query embedding are also request-only. An unchecked, optional per-match control may retain the primary normalized JPEG and vector for a configured period. Record the consent text version and timestamp. Encrypt the JPEG before PostgreSQL storage; permit withdrawal by the user and audited image/vector access by administrators only. Never retain the second self-check image.
- Require an administrator-provisioned account for every application API except health. Use Argon2id password hashes, opaque server-side sessions, secure HttpOnly SameSite cookies, an eight-hour session lifetime, and account disablement that revokes all sessions.
- Store only hashed, 24-hour invitation tokens. Show the token once in the admin UI; place it in the URL fragment so it is not sent in HTTP requests or ordinary server access logs.
- Record match timestamp, user, status/reason, duration, model version, and up to five candidate names/IDs and scores for 30 days. Without explicit retention consent, do not store the source image, query embedding, IP address, or image metadata. The admin panel exposes inference metadata and separately gated consented uploads.
- Record sign-ins, password setup/reset, duel loads, and votes in a separate user-activity log for up to 365 days. The admin panel exposes the recent activity stream.
- Record account, role, login, and admin log-view actions in an application-level audit log. Do not put passwords, raw invitation/session tokens, image bytes, or embeddings into logs. Keep audit details free of secrets; rotate/prune failed-login and other security records according to the production retention policy.
- Apply per-IP and per-account inference throttles, response security headers, same-origin UI/API, and a non-root container user. Keep Postgres private to Render's network.
- Structured request logs contain only route templates, status, duration, deployment/experiment labels, and generated request/trace IDs. They exclude query strings, bodies, image metadata, IP addresses, account identifiers, session/invite tokens, embeddings, and similarity scores.
- Before public launch, add an explicit data notice and an appropriate bot defense for voting. Review whether face embeddings in this use case trigger additional data-protection obligations. Add MFA for administrators before inviting a wider group.

## Consequences

The upload endpoint fails closed while matching is disabled, the model is unavailable, or the reference gallery is empty. The built-in IP limiter is per process and is only a baseline; production multi-instance deployments require a shared limiter or edge-level control. The 30-day inference cleanup runs opportunistically on API traffic; a scheduled cleanup job is preferable for strict expiry when the service receives no traffic.
