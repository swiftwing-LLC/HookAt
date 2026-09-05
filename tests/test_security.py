from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from backend.api import HookAtAPI
from backend.config import Config
from backend.services.deepseek_service import DeepSeekService, minimize_candidate, minimize_criteria, stable_hash
from tests.test_profiles_criteria import ApiCase


class SecurityTests(ApiCase):
    def test_frontend_bundle_does_not_contain_api_key_markers(self):
        frontend_files = list(Path("002").glob("*.js")) + list(Path("002").glob("*.html")) + list(Path("002").glob("*.css"))
        combined = "\n".join(path.read_text(encoding="utf-8") for path in frontend_files)
        self.assertNotIn("DEEPSEEK" + "_API_KEY", combined)
        self.assertNotIn("service" + "_role", combined)
        self.assertNotIn("sk" + "-", combined)

    def test_cors_rejects_unknown_origin(self):
        response = self.api.handle(
            "GET",
            "/api/config",
            {"Origin": "https://evil.example", "X-Anonymous-User-Id": self.anon},
            b"",
            client_ip="cors-test",
        )
        self.assertEqual(response.status, 403)
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_rate_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                database_url=f"sqlite:///{Path(tmpdir) / 'rate.db'}",
                frontend_origins=["http://localhost:8000"],
                rate_limit_requests=1,
            )
            api = HookAtAPI(config)
            headers = {"Origin": "http://localhost:8000", "X-Anonymous-User-Id": str(uuid.uuid4())}
            first = api.handle("GET", "/api/config", headers, b"", client_ip="rate-test")
            second = api.handle("GET", "/api/config", headers, b"", client_ip="rate-test")
            self.assertEqual(first.status, 200)
            self.assertEqual(second.status, 429)

    def test_delete_profile_cleans_semantic_cache(self):
        def transport(payload, timeout):
            content = json.dumps(
                {
                    "semantic_score": 80,
                    "matched_reasons": ["Shared interests"],
                    "unmatched_preferences": [],
                    "confidence": "medium",
                }
            )
            return 200, {"choices": [{"message": {"content": content}}]}

        profile = self.create_profile()
        criteria_response = self.request(
            "POST",
            f"/api/profiles/{profile['id']}/criteria",
            {"target_type": "Women", "interests": ["chemistry"]},
        )
        criteria = criteria_response.body["data"]["criteria"]
        candidate = next(item for item in self.api.db.list_match_candidates(profile["id"]) if item["name"] == "Sloane")
        self.config.deepseek_api_key = "test-key"
        service = DeepSeekService(self.config, self.api.db, transport=transport)
        service.score(criteria, candidate, 90)

        criteria_hash = stable_hash(minimize_criteria(criteria))
        candidate_hash = stable_hash(minimize_candidate(candidate))
        cached = self.api.db.get_semantic_cache(profile["id"], candidate["id"], criteria_hash, candidate_hash, self.config.deepseek_model)
        self.assertIsNotNone(cached)

        deleted = self.request("DELETE", f"/api/profiles/{profile['id']}")
        self.assertEqual(deleted.status, 200)
        cached_after_delete = self.api.db.get_semantic_cache(
            profile["id"],
            candidate["id"],
            criteria_hash,
            candidate_hash,
            self.config.deepseek_model,
        )
        self.assertIsNone(cached_after_delete)


if __name__ == "__main__":
    unittest.main()
