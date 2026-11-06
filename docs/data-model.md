# Data model

## Accounts and authorization

- `users`: UUID `id`, unique normalized `email`, nullable Argon2id `password_hash`, `role` (`user` or `admin`), account `status`, optional creator, creation time, and last-login time. Admins are ordinary users with `role=admin`; there is no parallel admin credential table.
- `auth_sessions`: UUID, user FK, SHA-256 digest of an opaque random cookie token, expiry, and creation time. Raw tokens exist only in the Secure/HttpOnly/SameSite cookie.
- `invitations`: UUID, user FK, SHA-256 digest of a one-time random token, purpose, expiry, acceptance time, and creation time. The raw token is shown once in a URL fragment.
- `bootstrap_state`: singleton marking first-admin setup as consumed.
- `admin_audit_events` and `user_activity_events`: actor/user references, action, non-secret JSON details, and timestamps.

## Reference and query vectors

- `celebrities`: legacy technical table name for both gallery and guest rating candidates. It stores a stable ID, display nickname/name, candidate type, optional owner/consented-upload links, one optional gallery portrait, Hot or Not activation, Elo state, the last Hot or Not appearance used for fair guest queueing, and timestamps. Guest rows never store plaintext image bytes; they point to the encrypted consented upload.
- `face_samples`: gallery identity FK, source/provenance fields, and a 128-dimensional pgvector SFace embedding. Multiple samples support retrieval; the one optional display portrait lives on the candidate row instead of being duplicated per sample.
- `inference_events`: requesting user, request ID, outcome/reason, duration, model version, and top public candidate names/IDs/scores. It has no image or query vector by default.
- `consented_uploads`: one-to-one inference FK, owner, separately Fernet-encrypted normalized JPEG and 128-dimensional query vector, media types, vector dimension, model/key/retention-consent versions, optional Hot or Not consent version/time, expiry, and creation time. Admin image/vector access remains audited. An active Hot or Not consent additionally permits signed-in players to view only the portrait through its candidate endpoint. Owner/admin deletion or expiry unlinks and deactivates the candidate while retaining anonymized Elo history.

A SFace embedding is a lossy, normalized identity-feature representation. It cannot reproduce the original pixels. Model-inversion techniques may synthesize an approximation, which is why the vector is treated as biometric data, but they cannot recover the actual upload.
