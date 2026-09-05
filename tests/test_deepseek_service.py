from __future__ import annotations

import json

from backend.services.deepseek_service import DeepSeekService, minimize_candidate, minimize_criteria
from tests.test_profiles_criteria import ApiCase


class DeepSeekServiceTests(ApiCase):
    def create_candidate_context(self):
        profile = self.create_profile()
        criteria_response = self.request(
            "POST",
            f"/api/profiles/{profile['id']}/criteria",
            {
                "target_type": "Women",
                "interests": ["chemistry"],
                "preferred_conditions": {"intent": "Direct chemistry"},
                "free_text_requirement": "direct chemistry",
            },
        )
        self.assertEqual(criteria_response.status, 201, criteria_response.body)
        criteria = criteria_response.body["data"]["criteria"]
        candidates = self.api.db.list_match_candidates(profile["id"])
        candidate = next(item for item in candidates if item["name"] == "Sloane")
        return criteria, candidate

    def test_deepseek_valid_response_is_parsed_and_cached(self):
        calls = {"count": 0}

        def transport(payload, timeout):
            calls["count"] += 1
            user_content = payload["messages"][1]["content"]
            self.assertNotIn("Sloane", user_content)
            content = json.dumps(
                {
                    "semantic_score": 78,
                    "matched_reasons": ["Shared interests"],
                    "unmatched_preferences": [],
                    "confidence": "medium",
                }
            )
            return 200, {"choices": [{"message": {"content": content}}]}

        config = self.config
        config.deepseek_api_key = "test-key"
        service = DeepSeekService(config, self.api.db, transport=transport)
        criteria, candidate = self.create_candidate_context()

        first = service.score(criteria, candidate, 90)
        second = service.score(criteria, candidate, 90)

        self.assertEqual(first.semantic_score, 78)
        self.assertEqual(first.source, "ai")
        self.assertEqual(second.source, "cache")
        self.assertEqual(calls["count"], 1)

    def test_deepseek_timeout_falls_back_to_structured_score(self):
        def transport(payload, timeout):
            raise TimeoutError("boom")

        self.config.deepseek_api_key = "test-key"
        self.config.deepseek_retries = 0
        service = DeepSeekService(self.config, self.api.db, transport=transport)
        criteria, candidate = self.create_candidate_context()

        result = service.score(criteria, candidate, 87)

        self.assertEqual(result.semantic_score, 87)
        self.assertTrue(result.source.startswith("fallback:"))

    def test_deepseek_invalid_json_does_not_crash(self):
        def transport(payload, timeout):
            return 200, {"choices": [{"message": {"content": "not json"}}]}

        self.config.deepseek_api_key = "test-key"
        self.config.deepseek_retries = 0
        service = DeepSeekService(self.config, self.api.db, transport=transport)
        criteria, candidate = self.create_candidate_context()

        result = service.score(criteria, candidate, 64)

        self.assertEqual(result.semantic_score, 64)
        self.assertTrue(result.source.startswith("fallback:"))

    def test_deepseek_score_out_of_range_is_clamped(self):
        def transport(payload, timeout):
            content = json.dumps(
                {
                    "semantic_score": 140,
                    "matched_reasons": ["Shared interests"],
                    "unmatched_preferences": [],
                    "confidence": "high",
                }
            )
            return 200, {"choices": [{"message": {"content": content}}]}

        self.config.deepseek_api_key = "test-key"
        service = DeepSeekService(self.config, self.api.db, transport=transport)
        criteria, candidate = self.create_candidate_context()

        result = service.score(criteria, candidate, 70)

        self.assertEqual(result.semantic_score, 100)
        self.assertEqual(result.confidence, "low")

    def test_payload_minimization_excludes_name(self):
        criteria, candidate = self.create_candidate_context()
        minimized = minimize_candidate(candidate)
        serialized = json.dumps({"criteria": minimize_criteria(criteria), "candidate": minimized})
        self.assertNotIn(candidate["name"], serialized)
        self.assertNotIn("email", serialized)

