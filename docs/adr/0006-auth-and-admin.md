# ADR 0006: Invite-only authentication and admin visibility

- Status: Accepted for MVP; administrator MFA and production review remain launch gates
- Date: 2026-11-01

## Decision

- No public registration. An active administrator creates an account with a `user` or `admin` role and shares a one-time invitation link with a 24-hour expiry. The app stores only a SHA-256 digest of the invite token; the raw token is shown once and carried in the URL fragment.
- The invited person sets their own password. Passwords are hashed with Argon2id. Sessions are opaque random tokens stored only as digests in Postgres, set in Secure/HttpOnly/SameSite=Strict cookies, expire after eight hours, and are checked against current account status/role on every request.
- All application API routes except health require an active session. Admin operations require the admin role. Disabling an account revokes its sessions. The last active admin cannot disable or demote themselves.
- Admins can review user accounts, active status/role, last login, and inference usage. Inference events contain user, time, request ID, status/reason, duration, model version, and up to five public candidate names/IDs and similarity scores. Events expire after 30 days. ADR 0009 separately permits explicitly consented encrypted images and embeddings with expiry, withdrawal, and audited admin-only access; IP addresses are not recorded.
- Sign-ins, password setup/reset, Hot or Not matchup loads, and votes are recorded as user-activity metadata for 365 days so administrators can review app usage.
- Admin account changes, login outcomes, and access to admin dashboards/logs are written to an application audit table, retained for 365 days. The UI offers admin-created password reset links and repeat activation invites.
- First-admin creation supports `INITIAL_ADMIN_EMAIL` plus `INITIAL_ADMIN_PASSWORD` in Render environment configuration. Startup creates the account only when no active admin exists, under a database advisory lock; the launcher removes both values from the web-process environment after bootstrap. Operators must remove the values from Render and redeploy. The guarded `BOOTSTRAP_SECRET` one-time HTTPS setup remains a fallback. Passwords are never placed in source control or command arguments.

## Consequences

- The app can identify excessive inference volume and failures, but these are review signals, not automated accusations or enforcement decisions. Per-IP limits are process-local; deployments with multiple instances need shared rate limiting.
- Inference metadata is still personal data and can reveal user activity. The 30-day retention and admin review must be stated clearly to users. Expiry currently runs opportunistically on API traffic; strict deletion while idle needs a scheduled job.
- Admin sessions are not protected with a second factor in this MVP. Add MFA and stronger audit-log integrity before broader exposure.
- Free Render web services have no Shell/SSH, pre-deploy command, or one-off job. Migrations run during single-instance service startup. The first-admin setup endpoint avoids shell access, but Free Postgres expires after 30 days and Free web services sleep when idle; this is suitable for a temporary demo, not durable production hosting.
- On Free, invite a second trusted admin as the practical account-recovery path. There is no direct shell-based recovery if all admin credentials are lost.
