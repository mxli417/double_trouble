"""Create the first administrator interactively after database migrations."""

import argparse
import getpass
import re
import sys
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, func, select, text

from app.auth import audit, password_hash
from app.db import SessionLocal
from app.models import AuthSession, BootstrapState, User


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap or recover the first administrator")
    parser.add_argument("email", nargs="?")
    parser.add_argument("--reset", action="store_true", help="reset password for an existing admin and revoke sessions")
    args = parser.parse_args()
    email = (args.email or input("Admin email: ")).strip().casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        print("Enter a valid email address.", file=sys.stderr)
        return 2
    first = getpass.getpass("Set admin password (12+ characters): ")
    second = getpass.getpass("Confirm password: ")
    if len(first) < 12 or first != second:
        print("Passwords must match and contain at least 12 characters.", file=sys.stderr)
        return 2

    with SessionLocal.begin() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(88445291)"))
        existing = db.scalar(select(User).where(User.email == email).with_for_update())
        if args.reset:
            if not existing or existing.role != "admin":
                print("No administrator account exists for that email.", file=sys.stderr)
                return 3
            existing.password_hash = password_hash.hash(first)
            existing.status = "active"
            db.execute(delete(AuthSession).where(AuthSession.user_id == existing.id))
            audit(db, "admin.password_reset.bootstrap", actor_id=existing.id, subject_user_id=existing.id)
            if db.get(BootstrapState, 1) is None:
                db.add(BootstrapState(id=1, completed_at=datetime.now(UTC)))
            print(f"Admin password reset for {email}; existing sessions were revoked.")
            return 0
        active_admins = db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.status == "active")) or 0
        if active_admins:
            print("An active admin already exists. Use the Admin Panel to invite more administrators.", file=sys.stderr)
            return 3
        if existing and existing.status != "disabled":
            print("That email already belongs to an account.", file=sys.stderr)
            return 3
        if existing:
            existing.role = "admin"
            existing.status = "active"
            existing.password_hash = password_hash.hash(first)
            bootstrap_user = existing
        else:
            created = User(id=str(uuid4()), email=email, role="admin", status="active", password_hash=password_hash.hash(first))
            db.add(created)
            db.flush()
            bootstrap_user = created
        if db.get(BootstrapState, 1) is None:
            db.add(BootstrapState(id=1, completed_at=datetime.now(UTC)))
        audit(db, "admin.bootstrap", actor_id=bootstrap_user.id, subject_user_id=bootstrap_user.id)
    print(f"Admin account ready for {email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
