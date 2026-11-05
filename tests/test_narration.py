import os
import unittest
from unittest.mock import patch

from app.config import get_settings
from app.narration import narrate_match


class _FakeResponses:
    def __init__(self):
        self.arguments = None

    async def create(self, **kwargs):
        self.arguments = kwargs
        return type("FakeResponse", (), {"output_text": "A playful synthetic result."})()


class _FakeClient:
    def __init__(self):
        self.responses = _FakeResponses()


class NarrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_narration_sends_only_candidates_and_disables_storage(self):
        fake = _FakeClient()
        environment = {"MATCH_NARRATION_ENABLED": "true", "OPENAI_API_KEY": "test-key"}
        with patch.dict(os.environ, environment), patch("app.narration.AsyncOpenAI", return_value=fake):
            get_settings.cache_clear()
            result = await narrate_match([{"name": "Synthetic Person", "similarity": 0.75}])
        get_settings.cache_clear()
        self.assertEqual(result, "A playful synthetic result.")
        self.assertFalse(fake.responses.arguments["store"])
        self.assertIn("Synthetic Person", fake.responses.arguments["input"])
        self.assertNotIn("image", fake.responses.arguments["input"].casefold())


if __name__ == "__main__":
    unittest.main()
