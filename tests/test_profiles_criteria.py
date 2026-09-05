from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from backend.api import HookAtAPI
from backend.config import Config


class ApiCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "test.db"
        self.config = Config(
            database_url=f"sqlite:///{db_path}",
            frontend_origins=["http://localhost:8000"],
            rate_limit_requests=1000,
        )
        self.api = HookAtAPI(self.config)
        self.anon = str(uuid.uuid4())
        self.headers = {
            "Content-Type": "application/json",
            "X-Anonymous-User-Id": self.anon,
            "Origin": "http://localhost:8000",
        }

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def request(self, method: str, path: str, payload: dict | None = None, headers: dict | None = None):
        body = json.dumps(payload or {}).encode("utf-8") if payload is not None else b""
        return self.api.handle(method, path, headers or self.headers, body, client_ip="test")

    def create_profile(self, name: str = " Alice Smith "):
        response = self.request(
            "POST",
            "/api/profiles",
            {
                "name": name,
                "age": 28,
                "city": "New York",
                "seeking": "Women",
                "intent": "Direct chemistry",
                "bio": "Clear plans and consent.",
            },
        )
        self.assertIn(response.status, (200, 201), response.body)
        return response.body["data"]["profile"]


class ProfileCriteriaTests(ApiCase):
    def test_normal_name_is_saved_trimmed(self):
        profile = self.create_profile()
        self.assertEqual(profile["name"], "Alice Smith")
        self.assertIsNotNone(profile["id"])
        self.assertFalse(profile["allow_matching"])
        self.assertEqual(profile["visibility"], "private")

    def test_empty_name_is_rejected(self):
        response = self.request("POST", "/api/profiles", {"name": "   "})
        self.assertEqual(response.status, 400)
        self.assertFalse(response.body["success"])

    def test_long_name_is_rejected(self):
        response = self.request("POST", "/api/profiles", {"name": "a" * 101})
        self.assertEqual(response.status, 400)
        self.assertFalse(response.body["success"])

    def test_bad_profile_id_is_rejected(self):
        response = self.request("GET", "/api/profiles/not-a-uuid")
        self.assertEqual(response.status, 400)
        self.assertFalse(response.body["success"])

    def test_user_cannot_modify_other_profile(self):
        profile = self.create_profile()
        other_headers = dict(self.headers)
        other_headers["X-Anonymous-User-Id"] = str(uuid.uuid4())
        response = self.request("PATCH", f"/api/profiles/{profile['id']}", {"name": "Mallory"}, other_headers)
        self.assertEqual(response.status, 403)

    def test_criteria_can_be_created_and_updated(self):
        profile = self.create_profile()
        response = self.request(
            "POST",
            f"/api/profiles/{profile['id']}/criteria",
            {
                "target_type": "Women",
                "location": "New York",
                "age_min": 25,
                "age_max": 35,
                "interests": ["consent", "nearby"],
                "required_conditions": {"adult": True},
                "preferred_conditions": {"intent": "Direct chemistry"},
                "free_text_requirement": "Direct, respectful energy.",
            },
        )
        self.assertEqual(response.status, 201, response.body)
        criteria = response.body["data"]["criteria"]
        self.assertEqual(criteria["target_type"], "Women")

        patch = self.request(
            "PATCH",
            f"/api/profiles/{profile['id']}/criteria",
            {"age_max": 40, "interests": ["consent"]},
        )
        self.assertEqual(patch.status, 200, patch.body)
        updated = patch.body["data"]["criteria"]
        self.assertEqual(updated["age_max"], 40)
        self.assertEqual(updated["interests"], ["consent"])

    def test_delete_profile_removes_criteria(self):
        profile = self.create_profile()
        self.request("POST", f"/api/profiles/{profile['id']}/criteria", {"target_type": "Women"})
        deleted = self.request("DELETE", f"/api/profiles/{profile['id']}")
        self.assertEqual(deleted.status, 200)
        criteria = self.request("GET", f"/api/profiles/{profile['id']}/criteria")
        self.assertEqual(criteria.status, 404)


if __name__ == "__main__":
    unittest.main()
