from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from ..config import Config
from ..db import Database
from .matching_service import clamp_score


Transport = Callable[[dict[str, Any], float], tuple[int, dict[str, Any]]]


SYSTEM_PROMPT = """You are a matching assistant.

Evaluate compatibility only from the explicitly provided criteria and
candidate attributes.

Do not infer any missing personal, medical, demographic, religious,
racial, political, sexual, or socioeconomic attributes.

Hard requirements have already been evaluated by the backend.
You must not override hard requirements.

Return valid JSON only.

Score semantic compatibility from 0 to 100.
Provide concise reasons grounded only in the supplied data.
Clearly distinguish positive matches from unmet preferences.
Do not fabricate facts."""


GENERIC_REASON_TOKENS = {
    "age",
    "and",
    "candidate",
    "compatible",
    "condition",
    "conditions",
    "criteria",
    "direct",
    "free",
    "grounded",
    "interest",
    "interests",
    "intent",
    "location",
    "match",
    "matched",
    "matches",
    "matching",
    "met",
    "not",
    "overlap",
    "preference",
    "preferences",
    "profile",
    "provided",
    "requirement",
    "requirements",
    "satisfied",
    "shared",
    "text",
    "unmet",
}


SENSITIVE_TOKENS = {
    "race",
    "racial",
    "religion",
    "religious",
    "disease",
    "medical",
    "diagnosis",
    "sexuality",
    "orientation",
    "political",
    "income",
    "socioeconomic",
}


@dataclass(slots=True)
class SemanticResult:
    semantic_score: int
    matched_reasons: list[str]
    unmatched_preferences: list[str]
    confidence: str
    source: str
    error_type: str | None = None


class SimpleWindowLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self.hits: list[float] = []
        self.lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self.lock:
            self.hits = [ts for ts in self.hits if ts >= cutoff]
            if len(self.hits) >= self.limit:
                return False
            self.hits.append(now)
            return True


class DeepSeekService:
    def __init__(self, config: Config, db: Database, transport: Transport | None = None):
        self.config = config
        self.db = db
        self.transport = transport or self._http_transport
        self.rate_limiter = SimpleWindowLimiter(config.ai_rate_limit_requests)
        self.semaphore = threading.BoundedSemaphore(max(1, config.deepseek_concurrency))

    def score(self, criteria: dict[str, Any], candidate: dict[str, Any], structured_score: int) -> SemanticResult:
        if self.config.normalized_storage_mode() == "local":
            return fallback_result(structured_score, "local_demo_mode")
        if not self.config.deepseek_api_key:
            return fallback_result(structured_score, "missing_api_key")

        criteria_payload = minimize_criteria(criteria)
        candidate_payload = minimize_candidate(candidate)
        criteria_hash = stable_hash(criteria_payload)
        candidate_hash = stable_hash(candidate_payload)
        cached = self.db.get_semantic_cache(criteria["profile_id"], candidate["id"], criteria_hash, candidate_hash, self.config.deepseek_model)
        if cached:
            return SemanticResult(
                semantic_score=clamp_score(cached["semantic_score"]),
                matched_reasons=cached["matched_reasons"],
                unmatched_preferences=cached["unmatched_preferences"],
                confidence=cached["confidence"],
                source="cache",
            )

        if not self.rate_limiter.allow():
            self.db.write_audit_event("deepseek_score", "fallback", self.config.deepseek_model, None, "rate_limited", 0)
            return fallback_result(structured_score, "rate_limited")

        request_id = str(uuid.uuid4())
        started = time.monotonic()
        try:
            with self.semaphore:
                result = self._request_with_retry(criteria_payload, candidate_payload)
            latency_ms = int((time.monotonic() - started) * 1000)
            self.db.write_audit_event("deepseek_score", "success", self.config.deepseek_model, 200, None, latency_ms, request_id)
            self.db.set_semantic_cache(
                owner_profile_id=criteria["profile_id"],
                candidate_profile_id=candidate["id"],
                criteria_hash=criteria_hash,
                candidate_hash=candidate_hash,
                model=self.config.deepseek_model,
                result=result,
            )
            return result
        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            error_type = exc.__class__.__name__
            self.db.write_audit_event("deepseek_score", "fallback", self.config.deepseek_model, None, error_type, latency_ms, request_id)
            return fallback_result(structured_score, error_type)

    def _request_with_retry(self, criteria_payload: dict[str, Any], candidate_payload: dict[str, Any]) -> SemanticResult:
        last_error: Exception | None = None
        for _attempt in range(max(0, self.config.deepseek_retries) + 1):
            try:
                status, response = self.transport(self._build_request(criteria_payload, candidate_payload), self.config.deepseek_timeout_seconds)
                if status < 200 or status >= 300:
                    raise RuntimeError(f"deepseek_http_{status}")
                return parse_deepseek_response(response, criteria_payload, candidate_payload)
            except Exception as exc:
                last_error = exc
        raise last_error or RuntimeError("deepseek_failed")

    def _build_request(self, criteria_payload: dict[str, Any], candidate_payload: dict[str, Any]) -> dict[str, Any]:
        user_payload = {
            "criteria": criteria_payload,
            "candidate": candidate_payload,
            "expected_schema": {
                "semantic_score": "number 0-100",
                "matched_reasons": "string[]",
                "unmatched_preferences": "string[]",
                "confidence": "low|medium|high",
            },
        }
        return {
            "model": self.config.deepseek_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True)},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

    def _http_transport(self, payload: dict[str, Any], timeout: float) -> tuple[int, dict[str, Any]]:
        url = f"{self.config.deepseek_base_url.rstrip('/')}/chat/completions"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.deepseek_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
                return response.status, body
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode("utf-8"))
            except Exception:
                body = {}
            return exc.code, body


def parse_deepseek_response(
    response: dict[str, Any],
    criteria_payload: dict[str, Any],
    candidate_payload: dict[str, Any],
) -> SemanticResult:
    content = extract_content(response)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_json") from exc
    if not isinstance(parsed, dict):
        raise ValueError("invalid_schema")

    score = parsed.get("semantic_score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise ValueError("invalid_score")

    confidence = parsed.get("confidence", "low")
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"

    allowed_tokens = grounding_tokens(criteria_payload, candidate_payload)
    matched = validate_reason_list(parsed.get("matched_reasons"), allowed_tokens)
    unmatched = validate_reason_list(parsed.get("unmatched_preferences"), allowed_tokens)
    corrected_score = clamp_score(score)
    if corrected_score != round(float(score)):
        confidence = "low"

    return SemanticResult(
        semantic_score=corrected_score,
        matched_reasons=matched,
        unmatched_preferences=unmatched,
        confidence=confidence,
        source="ai",
    )


def extract_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing_choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ValueError("missing_message")
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("missing_content")
    return content


def validate_reason_list(value: Any, allowed_tokens: set[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("invalid_reason_list")
    reasons: list[str] = []
    for item in value[:8]:
        if not isinstance(item, str):
            raise ValueError("invalid_reason")
        text = item.strip()
        if not text or len(text) > 180:
            continue
        tokens = tokenize(text)
        if tokens & SENSITIVE_TOKENS:
            continue
        unsupported = tokens - allowed_tokens - GENERIC_REASON_TOKENS
        if unsupported:
            continue
        reasons.append(text)
    return reasons


def grounding_tokens(criteria_payload: dict[str, Any], candidate_payload: dict[str, Any]) -> set[str]:
    serialized = json.dumps({"criteria": criteria_payload, "candidate": candidate_payload}, ensure_ascii=False)
    return tokenize(serialized)


def tokenize(value: str) -> set[str]:
    from .matching_service import TOKEN_RE

    return {token for token in TOKEN_RE.findall(value.lower()) if len(token) > 2}


def minimize_criteria(criteria: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_type": criteria.get("target_type"),
        "location": criteria.get("location"),
        "age_min": criteria.get("age_min"),
        "age_max": criteria.get("age_max"),
        "interests": criteria.get("interests", []),
        "preferred_conditions": criteria.get("preferred_conditions", {}),
        "free_text_requirement": criteria.get("free_text_requirement"),
    }


def minimize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_id": candidate.get("id"),
        "age": candidate.get("age"),
        "city": candidate.get("city"),
        "gender": candidate.get("gender"),
        "intent": candidate.get("intent"),
        "interests": candidate.get("interests", []),
        "bio": candidate.get("bio"),
    }


def stable_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fallback_result(structured_score: int, error_type: str) -> SemanticResult:
    return SemanticResult(
        semantic_score=clamp_score(structured_score),
        matched_reasons=[],
        unmatched_preferences=[],
        confidence="low",
        source=f"fallback:{error_type}",
        error_type=error_type,
    )
