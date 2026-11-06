"""Initialize immutable deployment data before the HTTP server starts."""

import sys
from pathlib import Path

from app.bootstrap_env import main as bootstrap_administrator
from app.config import get_settings
from app.gallery import ingest_bundle


def main() -> int:
    settings = get_settings()
    if settings.gallery_required and (not settings.gallery_bundle_path or not settings.gallery_bundle_sha256):
        print(
            "GALLERY_REQUIRED needs both GALLERY_BUNDLE_PATH and GALLERY_BUNDLE_SHA256.",
            file=sys.stderr,
        )
        return 2
    if settings.gallery_bundle_path:
        ingest_bundle(Path(settings.gallery_bundle_path), settings.gallery_bundle_sha256)
    return bootstrap_administrator()


if __name__ == "__main__":
    raise SystemExit(main())
