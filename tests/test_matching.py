from __future__ import annotations

from tests.test_profiles_criteria import ApiCase


class MatchingTests(ApiCase):
    def create_criteria(self, profile_id: str, payload: dict):
        response = self.request("POST", f"/api/profiles/{profile_id}/criteria", payload)
        self.assertEqual(response.status, 201, response.body)
        return response.body["data"]["criteria"]

    def test_hard_filter_excludes_candidates_outside_age_range(self):
        profile = self.create_profile()
        criteria = self.create_criteria(
            profile["id"],
            {
                "target_type": "Women",
                "age_min": 28,
                "age_max": 30,
                "interests": ["chemistry"],
            },
        )

        response = self.request(
            "POST",
            "/api/matches/search",
            {"profile_id": profile["id"], "criteria_id": criteria["id"], "limit": 20},
        )

        self.assertEqual(response.status, 200, response.body)
        matches = response.body["data"]["matches"]
        self.assertEqual([match["profile"]["name"] for match in matches], ["Sloane"])
        self.assertTrue(all(match["profile"]["age"] >= 28 for match in matches))

    def test_required_condition_excludes_unmatched_candidate(self):
        profile = self.create_profile()
        criteria = self.create_criteria(
            profile["id"],
            {
                "target_type": "Women",
                "required_conditions": {"intent": "Tonight only"},
            },
        )

        response = self.request(
            "POST",
            "/api/matches/search",
            {"profile_id": profile["id"], "criteria_id": criteria["id"], "limit": 20},
        )

        self.assertEqual(response.status, 200, response.body)
        self.assertEqual(response.body["data"]["matches"], [])

