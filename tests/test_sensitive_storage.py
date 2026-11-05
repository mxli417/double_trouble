import os
import unittest
from unittest.mock import patch

from app.config import get_settings
from app.sensitive_storage import (
    decrypt_embedding,
    decrypt_image,
    encrypt_embedding,
    encrypt_image,
)


class SensitiveStorageTests(unittest.TestCase):
    def test_consented_image_round_trip_is_encrypted(self):
        environment = {
            "DATA_ENCRYPTION_KEY": "ZGV2LW9ubHktZG91YmxlLXRyb3VibGUta2V5LTAwMDE=",
            "CONSENTED_STORAGE_ENABLED": "true",
        }
        with patch.dict(os.environ, environment):
            get_settings.cache_clear()
            plaintext = b"synthetic-image-bytes"
            encrypted = encrypt_image(plaintext)
            self.assertNotIn(plaintext, encrypted)
            self.assertEqual(decrypt_image(encrypted), plaintext)
            vector = [0.1, -0.2, 0.3]
            encrypted_vector = encrypt_embedding(vector)
            self.assertNotIn(b"0.1", encrypted_vector)
            self.assertEqual(decrypt_embedding(encrypted_vector), vector)
        get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
