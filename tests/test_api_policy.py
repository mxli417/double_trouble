import unittest
from time import perf_counter
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app, current_user, get_db, settings
from app.models import User


class _FakeSession:
    def scalar(self, _statement):
        return 0

    def add(self, _model):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None


class ApiPolicyTests(unittest.TestCase):
    def tearDown(self):
        app.dependency_overrides.clear()

    def test_disabled_matching_keeps_documented_503(self):
        app.dependency_overrides[get_db] = _FakeSession
        app.dependency_overrides[current_user] = lambda: User(
            id="synthetic-user",
            email="synthetic@example.invalid",
            role="user",
            status="active",
        )
        with (
            patch.object(settings, "matching_enabled", False),
            patch("app.main._last_retention_sweep", perf_counter()),
        ):
            response = TestClient(app).post(
                "/api/match",
                content=b"synthetic-image",
                headers={"content-type": "image/jpeg"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Lookalike matching is not enabled yet")


if __name__ == "__main__":
    unittest.main()
