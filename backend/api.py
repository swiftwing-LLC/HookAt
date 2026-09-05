from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .config import Config
from .db import Database, public_profile
from .errors import ApiError, NotFoundError, RateLimitError, ValidationError
from .services.matching_service import MatchingService, validate_search_payload
from .validation import (
    clean_age,
    clean_bool,
    clean_intent,
    clean_interests,
    clean_json_object,
    clean_name,
    clean_target_type,
    clean_text,
    parse_json_body,
    require_anonymous_user_id,
    require_uuid,
    validate_age_range,
)


@dataclass(slots=True)
class ApiResponse:
    status: int
    body: dict[str, Any]
    headers: dict[str, str]


class InMemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self.hits: dict[str, list[float]] = {}

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        entries = [ts for ts in self.hits.get(key, []) if ts >= cutoff]
        if len(entries) >= self.limit:
            self.hits[key] = entries
            raise RateLimitError("Rate limit exceeded.")
        entries.append(now)
        self.hits[key] = entries


class HookAtAPI:
    def __init__(self, config: Config | None = None, db: Database | None = None):
        self.config = config or Config()
        self.db = db or Database(self.config)
        self.db.initialize()
        self.rate_limiter = InMemoryRateLimiter(self.config.rate_limit_requests)
        self.matching_service = MatchingService(self.db, self.config)

    def handle(
        self,
        method: str,
        raw_path: str,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
        *,
        client_ip: str = "local",
    ) -> ApiResponse:
        headers = normalize_headers(headers or {})
        request_id = headers.get("x-request-id") or str(uuid.uuid4())
        origin = headers.get("origin")
        response_headers = self._cors_headers(origin)
        response_headers["X-Request-Id"] = request_id

        try:
            if origin and origin not in self.config.frontend_origins:
                raise ApiError("Origin is not allowed.", status=403)
            if len(body) > self.config.max_body_bytes:
                raise ValidationError("Request body is too large.")

            path = urlparse(raw_path).path
            if method != "OPTIONS":
                self.rate_limiter.check(f"{client_ip}:{headers.get('x-anonymous-user-id', 'anonymous')}")

            data = self._route(method.upper(), path, headers, body)
            status = 201 if data.pop("_created", False) else 200
            return ApiResponse(status, {"success": True, "data": data, "error": None}, response_headers)
        except ApiError as exc:
            return ApiResponse(
                exc.status,
                {
                    "success": False,
                    "data": None,
                    "error": {"code": exc.code, "message": exc.message, "details": exc.details},
                },
                response_headers,
            )
        except Exception:
            return ApiResponse(
                500,
                {
                    "success": False,
                    "data": None,
                    "error": {"code": "internal_error", "message": "Internal server error.", "details": {}},
                },
                response_headers,
            )

    def _cors_headers(self, origin: str | None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Vary": "Origin",
            "Access-Control-Allow-Methods": "GET,POST,PATCH,DELETE,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,X-Anonymous-User-Id,X-Request-Id",
        }
        if origin in self.config.frontend_origins:
            headers["Access-Control-Allow-Origin"] = origin
        return headers

    def _route(self, method: str, path: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        if method == "OPTIONS":
            return {}

        parts = [part for part in path.strip("/").split("/") if part]
        if parts == ["api", "config"] and method == "GET":
            return {
                "storage_mode": self.config.normalized_storage_mode(),
                "matching_weights": {
                    "structured": self.config.structured_weight,
                    "semantic": self.config.semantic_weight,
                },
            }

        if parts == ["api", "profiles"] and method == "POST":
            return self._create_profile(headers, body)

        if len(parts) == 3 and parts[:2] == ["api", "profiles"]:
            profile_id = require_uuid(parts[2], "profile_id")
            if method == "GET":
                return self._get_profile(profile_id, headers)
            if method == "PATCH":
                return self._patch_profile(profile_id, headers, body)
            if method == "DELETE":
                return self._delete_profile(profile_id, headers)

        if len(parts) == 4 and parts[:2] == ["api", "profiles"] and parts[3] == "criteria":
            profile_id = require_uuid(parts[2], "profile_id")
            if method == "POST":
                return self._create_criteria(profile_id, headers, body)
            if method == "GET":
                return self._get_criteria(profile_id, headers)
            if method == "PATCH":
                return self._patch_criteria(profile_id, headers, body)

        if parts == ["api", "matches", "search"] and method == "POST":
            return self._search_matches(headers, body)

        raise NotFoundError("Endpoint was not found.")

    def _create_profile(self, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        anonymous_user_id = require_anonymous_user_id(headers)
        payload = validate_profile_payload(parse_json_body(body), partial=False)
        profile, created = self.db.upsert_profile(anonymous_user_id, payload)
        return {"profile": public_profile(profile), "_created": created}

    def _get_profile(self, profile_id: str, headers: dict[str, str]) -> dict[str, Any]:
        anonymous_user_id = require_anonymous_user_id(headers)
        profile = self.db.get_owned_profile(profile_id, anonymous_user_id)
        return {"profile": public_profile(profile)}

    def _patch_profile(self, profile_id: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        anonymous_user_id = require_anonymous_user_id(headers)
        payload = validate_profile_payload(parse_json_body(body), partial=True)
        profile = self.db.update_profile(profile_id, anonymous_user_id, payload)
        return {"profile": public_profile(profile)}

    def _delete_profile(self, profile_id: str, headers: dict[str, str]) -> dict[str, Any]:
        anonymous_user_id = require_anonymous_user_id(headers)
        self.db.delete_profile(profile_id, anonymous_user_id)
        return {"deleted": True}

    def _create_criteria(self, profile_id: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        anonymous_user_id = require_anonymous_user_id(headers)
        payload = validate_criteria_payload(parse_json_body(body), partial=False)
        criteria, created = self.db.upsert_criteria(profile_id, anonymous_user_id, payload)
        return {"criteria": criteria, "_created": created}

    def _get_criteria(self, profile_id: str, headers: dict[str, str]) -> dict[str, Any]:
        anonymous_user_id = require_anonymous_user_id(headers)
        self.db.get_owned_profile(profile_id, anonymous_user_id)
        criteria = self.db.get_criteria(profile_id)
        if not criteria:
            raise NotFoundError("Criteria was not found.")
        return {"criteria": criteria}

    def _patch_criteria(self, profile_id: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        anonymous_user_id = require_anonymous_user_id(headers)
        payload = validate_criteria_payload(parse_json_body(body), partial=True)
        criteria = self.db.update_criteria(profile_id, anonymous_user_id, payload)
        return {"criteria": criteria}

    def _search_matches(self, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        anonymous_user_id = require_anonymous_user_id(headers)
        profile_id, criteria_id, limit = validate_search_payload(parse_json_body(body))
        matches = self.matching_service.search(profile_id, criteria_id, anonymous_user_id, limit)
        return {"matches": matches}


def normalize_headers(headers: dict[str, str]) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items()}


def validate_profile_payload(payload: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not partial or "name" in payload:
        out["name"] = clean_name(payload.get("name"))
    if "age" in payload:
        out["age"] = clean_age(payload.get("age"))
    if "city" in payload:
        out["city"] = clean_text(payload.get("city"), "city", max_length=100)
    if "bio" in payload:
        out["bio"] = clean_text(payload.get("bio"), "bio", max_length=1000, allow_newlines=True, reject_markup=False)
    if "intent" in payload:
        out["intent"] = clean_intent(payload.get("intent"))
    if "seeking" in payload:
        seeking = payload.get("seeking")
        out["seeking"] = clean_target_type(seeking) if seeking is not None else None
    if "image_url" in payload:
        out["image_url"] = clean_text(payload.get("image_url"), "image_url", max_length=2048, reject_markup=True)
    if "interests" in payload:
        out["interests"] = clean_interests(payload.get("interests"))
    if "allow_matching" in payload:
        out["allow_matching"] = clean_bool(payload.get("allow_matching"), "allow_matching", default=False)
    if "visibility" in payload:
        visibility = clean_text(payload.get("visibility"), "visibility", max_length=40)
        if visibility not in {"private", "match_pool"}:
            raise ValidationError("visibility is not supported.", details={"field": "visibility"})
        out["visibility"] = visibility
    if not partial:
        out.setdefault("age", None)
        out.setdefault("city", None)
        out.setdefault("bio", None)
        out.setdefault("intent", None)
        out.setdefault("seeking", None)
        out.setdefault("image_url", None)
        out.setdefault("interests", [])
        out.setdefault("allow_matching", False)
        out.setdefault("visibility", "private")
    return out


def validate_criteria_payload(payload: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not partial or "target_type" in payload:
        out["target_type"] = clean_target_type(payload.get("target_type"))
    if "location" in payload:
        out["location"] = clean_text(payload.get("location"), "location", max_length=100)
    if "age_min" in payload or "age_max" in payload:
        age_min, age_max = validate_age_range(payload.get("age_min"), payload.get("age_max"))
        if "age_min" in payload:
            out["age_min"] = age_min
        if "age_max" in payload:
            out["age_max"] = age_max
    if "interests" in payload:
        out["interests"] = clean_interests(payload.get("interests"))
    if "required_conditions" in payload:
        out["required_conditions"] = clean_json_object(payload.get("required_conditions"), "required_conditions")
    if "preferred_conditions" in payload:
        out["preferred_conditions"] = clean_json_object(payload.get("preferred_conditions"), "preferred_conditions")
    if "free_text_requirement" in payload:
        out["free_text_requirement"] = clean_text(
            payload.get("free_text_requirement"),
            "free_text_requirement",
            max_length=2000,
            allow_newlines=True,
            reject_markup=False,
        )
    if not partial:
        out.setdefault("location", None)
        out.setdefault("age_min", None)
        out.setdefault("age_max", None)
        out.setdefault("interests", [])
        out.setdefault("required_conditions", {})
        out.setdefault("preferred_conditions", {})
        out.setdefault("free_text_requirement", None)
    return out


def dumps_response(response: ApiResponse) -> bytes:
    return json.dumps(response.body, ensure_ascii=False).encode("utf-8")
