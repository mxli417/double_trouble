import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.bootstrap_runtime import main as bootstrap_runtime
from app.gallery import file_sha256, ingest_bundle


class GalleryTests(unittest.TestCase):
    def test_required_gallery_needs_path_and_checksum(self):
        settings = SimpleNamespace(
            gallery_required=True,
            gallery_bundle_path="/app/gallery/bundle.gz",
            gallery_bundle_sha256=None,
        )
        with patch("app.bootstrap_runtime.get_settings", return_value=settings):
            self.assertEqual(bootstrap_runtime(), 2)

    def test_file_sha256_streams_expected_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle.gz"
            bundle.write_bytes(b"synthetic-gallery")
            self.assertEqual(
                file_sha256(bundle),
                "ab583b877d1519417320c6b823a10754eb6e63f739fde765b3f1b9d3e3f903db",
            )

    def test_ingest_rejects_checksum_before_database_access(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle.gz"
            bundle.write_bytes(b"not-the-reviewed-gallery")
            with (
                patch("app.gallery.SessionLocal") as session_local,
                self.assertRaisesRegex(SystemExit, "checksum"),
            ):
                ingest_bundle(bundle, "0" * 64)
            session_local.assert_not_called()


if __name__ == "__main__":
    unittest.main()
