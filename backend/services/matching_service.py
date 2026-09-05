from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from ..config import Config
from ..db import Database
from ..errors import NotFoundError, ValidationError


TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(slots=True)
class MatchScore:
    profile_id: str
    score: int
    structured_score: int
    semantic_score: int
    semantic_confidence: str
    semantic_source: str
    matched_reasons: list[str]
    unmatched_preferences: list[str]
    candidate: dict[str, Any]


class MatchingService:
    def __init__(self, db: Database, config: Config, deepseek: Any | None = None):
        self.db = db
        self.config = config
        if deepseek is None:
            from .deepseek_service import DeepSeekService

            deepseek = DeepSeekService(config, db)
        self.deepseek = deepseek

    def search(self, profile_id: str, criteria_id: str, anonymous_user_id: str, limit: int) -> list[dict[str, Any]]:
        owner = self.db.get_owned_profile(profile_id, anonymous_user_id)
        criteria = self.db.get_criteria(profile_id)
        if not criteria or criteria["id"] != criteria_id:
            raise NotFoundError("Criteria was not found.")

        matches: list[MatchScore] = []
        for candidate in self.db.list_match_candidates(owner["id"]):
            passed, hard_reasons = hard_filter_passes(criteria, candidate)
            if not passed:
                continue
            structured_value, matched, unmatched = calculate_structured_score(criteria, candidate)
            matched = [*hard_reasons, *matched]
            semantic = self.deepseek.score(criteria, candidate, structured_value)
            semantic_score = semantic.semantic_score
            final_score = combine_scores(structured_value, semantic_score, self.config.structured_weight, self.config.semantic_weight)
            matches.append(
                MatchScore(
                    profile_id=candidate["id"],
                    score=final_score,
                    structured_score=structured_value,
                    semantic_score=semantic_score,
                    semantic_confidence=semantic.confidence,
                    semantic_source=semantic.source,
                    matched_reasons=[*matched, *semantic.matched_reasons],
                    unmatched_preferences=[*unmatched, *semantic.unmatched_preferences],
                    candidate=candidate,
                )
            )

        matches.sort(key=lambda item: (-item.score, item.profile_id))
        return [serialize_match(match) for match in matches[:limit]]


def combine_scores(structured: int | float, semantic: int | float, structured_weight: float, semantic_weight: float) -> int:
    total_weight = structured_weight + semantic_weight
    if total_weight <= 0:
        structured_weight = 1.0
        semantic_weight = 0.0
        total_weight = 1.0
    value = (float(structured) * structured_weight + float(semantic) * semantic_weight) / total_weight
    return clamp_score(round(value))


def clamp_score(value: int | float) -> int:
    if math.isnan(float(value)):
        return 0
    return max(0, min(100, int(round(float(value)))))


def hard_filter_passes(criteria: dict[str, Any], candidate: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    target_type = criteria.get("target_type")
    if target_type and target_type != "Everyone" and candidate.get("gender") != target_type:
        return False, []
    if target_type and target_type != "Everyone":
        reasons.append("Target type requirement satisfied")

    age = candidate.get("age")
    age_min = criteria.get("age_min")
    age_max = criteria.get("age_max")
    if age_min is not None and (age is None or age < age_min):
        return False, []
    if age_max is not None and (age is None or age > age_max):
        return False, []
    if age_min is not None or age_max is not None:
        reasons.append("Age requirement satisfied")

    location = criteria.get("location")
    if location and normalize(candidate.get("city")) != normalize(location):
        return False, []
    if location:
        reasons.append("Location requirement satisfied")

    required = criteria.get("required_conditions") or {}
    for key, expected in required.items():
        if not required_condition_matches(key, expected, candidate):
            return False, []
    if required:
        reasons.append("Required conditions satisfied")

    return True, reasons


def required_condition_matches(key: str, expected: Any, candidate: dict[str, Any]) -> bool:
    normalized_key = normalize(key)
    if normalized_key in {"intent", "city", "gender"}:
        return normalize(candidate.get(normalized_key)) == normalize(expected)
    if normalized_key == "interests":
        expected_items = expected if isinstance(expected, list) else [expected]
        candidate_interests = {normalize(item) for item in candidate.get("interests", [])}
        return all(normalize(item) in candidate_interests for item in expected_items)
    if normalized_key == "exclude_profile_ids":
        return candidate.get("id") not in set(expected if isinstance(expected, list) else [expected])
    candidate_value = candidate.get(normalized_key)
    if isinstance(expected, bool):
        return bool(candidate_value) is expected
    return normalize(candidate_value) == normalize(expected)


def calculate_structured_score(criteria: dict[str, Any], candidate: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    matched: list[str] = []
    unmatched: list[str] = []
    score = 0.0

    score += score_location(criteria, candidate, matched)
    score += score_age(criteria, candidate, matched)
    score += score_interests(criteria, candidate, matched, unmatched)
    score += score_preferences(criteria, candidate, matched, unmatched)
    score += score_free_text(criteria, candidate, matched, unmatched)

    return clamp_score(score), matched, unmatched


def score_location(criteria: dict[str, Any], candidate: dict[str, Any], matched: list[str]) -> float:
    if not criteria.get("location"):
        return 20.0
    matched.append("Candidate is in the requested location")
    return 20.0


def score_age(criteria: dict[str, Any], candidate: dict[str, Any], matched: list[str]) -> float:
    if criteria.get("age_min") is None and criteria.get("age_max") is None:
        return 20.0
    matched.append("Candidate is within the requested age range")
    return 20.0


def score_interests(
    criteria: dict[str, Any],
    candidate: dict[str, Any],
    matched: list[str],
    unmatched: list[str],
) -> float:
    desired = {normalize(item) for item in criteria.get("interests", []) if normalize(item)}
    if not desired:
        return 25.0
    actual = {normalize(item) for item in candidate.get("interests", []) if normalize(item)}
    overlap = desired & actual
    if overlap:
        matched.append("Shared interests")
    missing = sorted(desired - actual)
    if missing:
        unmatched.append("Some preferred interests were not matched")
    return 25.0 * (len(overlap) / len(desired))


def score_preferences(
    criteria: dict[str, Any],
    candidate: dict[str, Any],
    matched: list[str],
    unmatched: list[str],
) -> float:
    preferred = criteria.get("preferred_conditions") or {}
    if not preferred:
        return 25.0
    points_per_item = 25.0 / max(len(preferred), 1)
    score = 0.0
    for key, expected in preferred.items():
        if required_condition_matches(key, expected, candidate):
            score += points_per_item
            matched.append(f"Preferred condition matched: {key}")
        else:
            unmatched.append(f"Preferred condition not satisfied: {key}")
    return score


def score_free_text(
    criteria: dict[str, Any],
    candidate: dict[str, Any],
    matched: list[str],
    unmatched: list[str],
) -> float:
    requirement = criteria.get("free_text_requirement")
    if not requirement:
        return 10.0
    required_tokens = tokens(requirement)
    candidate_tokens = tokens(" ".join(str(candidate.get(key) or "") for key in ("bio", "intent", "city")))
    if not required_tokens:
        return 10.0
    overlap = required_tokens & candidate_tokens
    if overlap:
        matched.append("Profile text overlaps with the free-text requirement")
    else:
        unmatched.append("Free-text requirement had no direct structured text overlap")
    return 10.0 * (len(overlap) / len(required_tokens))


def tokens(value: str) -> set[str]:
    stop_words = {"and", "or", "the", "a", "an", "to", "for", "with", "in", "on", "of", "is"}
    return {token for token in TOKEN_RE.findall(value.lower()) if token not in stop_words and len(token) > 2}


def normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def serialize_match(match: MatchScore) -> dict[str, Any]:
    candidate = match.candidate
    return {
        "profile_id": match.profile_id,
        "score": match.score,
        "structured_score": match.structured_score,
        "semantic_score": match.semantic_score,
        "semantic_confidence": match.semantic_confidence,
        "semantic_source": match.semantic_source,
        "matched_reasons": match.matched_reasons[:8],
        "unmatched_preferences": match.unmatched_preferences[:8],
        "profile": {
            "id": candidate["id"],
            "name": candidate["name"],
            "age": candidate.get("age"),
            "city": candidate.get("city"),
            "gender": candidate.get("gender"),
            "bio": candidate.get("bio"),
            "intent": candidate.get("intent"),
            "interests": candidate.get("interests", []),
            "image_url": candidate.get("image_url"),
        },
    }


def validate_search_payload(payload: dict[str, Any]) -> tuple[str, str, int]:
    from ..validation import require_uuid

    profile_id = require_uuid(payload.get("profile_id"), "profile_id")
    criteria_id = require_uuid(payload.get("criteria_id"), "criteria_id")
    limit_value = payload.get("limit", 20)
    if isinstance(limit_value, bool):
        raise ValidationError("limit must be an integer.", details={"field": "limit"})
    try:
        limit = int(limit_value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("limit must be an integer.", details={"field": "limit"}) from exc
    if limit < 1 or limit > 50:
        raise ValidationError("limit must be between 1 and 50.", details={"field": "limit"})
    return profile_id, criteria_id, limit
