"""Create the first administrator from one-time deployment environment variables."""

import re
import sys
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select, text

from app.auth import audit, password_hash
from app.config import get_settings
from app.db import SessionLocal
from app.models import BootstrapState, User


def main() -> int:
    settings = get_settings()
    email_value = settings.initial_admin_email
    password = settings.initial_admin_password
    if email_value is None and password is None:
        return 0
    if not email_value or not password:
        print("Both INITIAL_ADMIN_EMAIL and INITIAL_ADMIN_PASSWORD are required.", file=sys.stderr)
        return 2
    email = email_value.strip().casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(password) < 12:
        print("Initial admin email or password does not meet validation requirements.", file=sys.stderr)
        return 2
    with SessionLocal.begin() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(88445291)"))
        active_admins = db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.status == "active")) or 0
        if active_admins:
            return 0
        if db.scalar(select(User.id).where(User.email == email)):
            print("The initial admin email already belongs to a non-active-admin account.", file=sys.stderr)
            return 3
        user = User(id=str(uuid4()), email=email, role="admin", status="active", password_hash=password_hash.hash(password))
        db.add(user)
        db.flush()
        if db.get(BootstrapState, 1) is None:
            db.add(BootstrapState(id=1, completed_at=datetime.now(UTC)))
        audit(db, "admin.bootstrap.environment", actor_id=user.id, subject_user_id=user.id)
    print("Initial administrator created; remove the bootstrap environment variables and redeploy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
