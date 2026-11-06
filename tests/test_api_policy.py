import unittest
from time import perf_counter
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.main import app, current_user, get_db, settings, valid_candidate_name, vote
from app.models import Celebrity, Duel, User


class _FakeSession:
    def execute(self, _statement):
        return None

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

    def test_readiness_fails_closed_without_required_gallery(self):
        class _Provider:
            embedding_dim = 128

        app.dependency_overrides[get_db] = _FakeSession
        with (
            patch.object(settings, "gallery_required", True),
            patch.object(settings, "matching_enabled", True),
            patch("app.main.get_face_provider", return_value=_Provider()),
            patch("app.main._last_retention_sweep", perf_counter()),
        ):
            response = TestClient(app).get("/api/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "not_ready")
        self.assertEqual(
            response.json()["failures"],
            ["gallery_not_loaded", "hot_or_not_not_ready"],
        )

    def test_readiness_accepts_loaded_gallery_and_models(self):
        class _ReadySession(_FakeSession):
            results = iter((1, 2))

            def scalar(self, _statement):
                return next(self.results)

        class _Provider:
            embedding_dim = 128

        app.dependency_overrides[get_db] = _ReadySession
        with (
            patch.object(settings, "gallery_required", True),
            patch.object(settings, "matching_enabled", True),
            patch("app.main.get_face_provider", return_value=_Provider()),
            patch("app.main._last_retention_sweep", perf_counter()),
        ):
            response = TestClient(app).get("/api/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")

    def test_hot_or_not_requires_separate_retention_consent(self):
        app.dependency_overrides[get_db] = _FakeSession
        app.dependency_overrides[current_user] = lambda: User(
            id="synthetic-user",
            email="synthetic@example.invalid",
            role="user",
            status="active",
        )
        with patch("app.main._last_retention_sweep", perf_counter()):
            response = TestClient(app).post(
                "/api/match",
                content=b"synthetic-image",
                headers={
                    "content-type": "image/jpeg",
                    "x-hot-or-not-consent": "true",
                    "x-retention-consent": "false",
                },
            )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            "Hot or Not participation requires encrypted photo retention consent",
        )

    def test_hot_or_not_name_rejects_email(self):
        self.assertEqual(valid_candidate_name("  Neon   Tiger  "), "Neon Tiger")
        with self.assertRaisesRegex(HTTPException, "nickname"):
            valid_candidate_name("person@example.com")

    def test_authenticated_gallery_portrait_is_served_without_storage_headers(self):
        candidate = Celebrity(
            id="gallery-candidate",
            display_name="Synthetic Person",
            candidate_type="gallery",
            portrait_image=b"\xff\xd8synthetic-jpeg\xff\xd9",
            portrait_media_type="image/jpeg",
            is_hot_or_not_active=True,
        )

        class _PortraitSession:
            def get(self, _model, _identifier):
                return candidate

        app.dependency_overrides[get_db] = _PortraitSession
        app.dependency_overrides[current_user] = lambda: User(
            id="synthetic-user",
            email="synthetic@example.invalid",
            role="user",
            status="active",
        )
        with patch("app.main._last_retention_sweep", perf_counter()):
            response = TestClient(app).get("/api/hot-or-not/candidates/gallery-candidate/image")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.content, candidate.portrait_image)

    def test_vote_uses_existing_session_transaction(self):
        winner = Celebrity(id="winner", display_name="Winner", elo=1500, vote_count=0)
        loser = Celebrity(id="loser", display_name="Loser", elo=1500, vote_count=0)
        duel = Duel(id="duel", left_id=winner.id, right_id=loser.id)

        class _People:
            def all(self):
                return [loser, winner]

        class _VoteSession:
            committed = False
            rolled_back = False

            def scalar(self, _statement):
                return duel

            def scalars(self, _statement):
                return _People()

            def add(self, _model):
                return None

            def commit(self):
                self.committed = True

            def rollback(self):
                self.rolled_back = True

        session = _VoteSession()
        request = Request({"type": "http", "method": "POST", "path": "/api/duel/duel/vote", "headers": []})
        result = vote(
            duel.id,
            request,
            winner.id,
            session,
            User(id="voter", email="voter@example.invalid", role="user", status="active"),
        )

        self.assertTrue(result["ok"])
        self.assertTrue(session.committed)
        self.assertFalse(session.rolled_back)
        self.assertEqual(duel.winner_id, winner.id)


if __name__ == "__main__":
    unittest.main()
