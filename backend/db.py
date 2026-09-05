from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Config
from .errors import ForbiddenError, NotFoundError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_uuid() -> str:
    return str(uuid.uuid4())


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class Database:
    def __init__(self, config: Config):
        self.config = config
        self.path = config.database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            self._ensure_optional_columns(conn)
            self._seed_demo_profiles(conn)

    def _ensure_optional_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(user_profiles)").fetchall()}
        if "interests_json" not in columns:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN interests_json TEXT NOT NULL DEFAULT '[]'")

    def _seed_demo_profiles(self, conn: sqlite3.Connection) -> None:
        for profile in DEMO_PROFILES:
            existing = conn.execute("SELECT id FROM user_profiles WHERE id = ?", (profile["id"],)).fetchone()
            if existing:
                continue
            now = utc_now()
            conn.execute(
                """
                INSERT INTO user_profiles (
                    id, anonymous_user_id, name, age, city, gender, bio, intent, seeking, interests_json,
                    image_url, allow_matching, visibility, is_demo, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'match_pool', 1, ?, ?)
                """,
                (
                    profile["id"],
                    profile["anonymous_user_id"],
                    profile["name"],
                    profile["age"],
                    profile["city"],
                    profile["gender"],
                    profile["bio"],
                    profile["intent"],
                    profile["seeking"],
                    _json(profile["interests"]),
                    profile["image_url"],
                    now,
                    now,
                ),
            )

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM user_profiles WHERE id = ?", (profile_id,)).fetchone()
            return profile_from_row(row) if row else None

    def get_owned_profile(self, profile_id: str, anonymous_user_id: str) -> dict[str, Any]:
        profile = self.get_profile(profile_id)
        if not profile:
            raise NotFoundError("Profile was not found.")
        if profile["anonymous_user_id"] != anonymous_user_id:
            raise ForbiddenError("This profile does not belong to the current anonymous user.")
        return profile

    def upsert_profile(self, anonymous_user_id: str, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        now = utc_now()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM user_profiles WHERE anonymous_user_id = ? AND is_demo = 0",
                (anonymous_user_id,),
            ).fetchone()
            if existing:
                profile_id = existing["id"]
                conn.execute(
                    """
                    UPDATE user_profiles
                    SET name = ?, age = ?, city = ?, bio = ?, intent = ?, seeking = ?, interests_json = ?, image_url = ?,
                        allow_matching = ?, visibility = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        payload["name"],
                        payload.get("age"),
                        payload.get("city"),
                        payload.get("bio"),
                        payload.get("intent"),
                        payload.get("seeking"),
                        _json(payload.get("interests", [])),
                        payload.get("image_url"),
                        int(payload.get("allow_matching", False)),
                        payload.get("visibility", "private"),
                        now,
                        profile_id,
                    ),
                )
                conn.commit()
                return self.get_profile(profile_id) or {}, False

            profile_id = new_uuid()
            conn.execute(
                """
                INSERT INTO user_profiles (
                    id, anonymous_user_id, name, age, city, bio, intent, seeking, interests_json, image_url,
                    allow_matching, visibility, is_demo, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    profile_id,
                    anonymous_user_id,
                    payload["name"],
                    payload.get("age"),
                    payload.get("city"),
                    payload.get("bio"),
                    payload.get("intent"),
                    payload.get("seeking"),
                    _json(payload.get("interests", [])),
                    payload.get("image_url"),
                    int(payload.get("allow_matching", False)),
                    payload.get("visibility", "private"),
                    now,
                    now,
                ),
            )
            conn.commit()
            return self.get_profile(profile_id) or {}, True

    def update_profile(self, profile_id: str, anonymous_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.get_owned_profile(profile_id, anonymous_user_id)
        if not payload:
            return self.get_profile(profile_id) or {}
        fields: list[str] = []
        values: list[Any] = []
        for column in ("name", "age", "city", "bio", "intent", "seeking", "image_url", "visibility"):
            if column in payload:
                fields.append(f"{column} = ?")
                values.append(payload[column])
        if "interests" in payload:
            fields.append("interests_json = ?")
            values.append(_json(payload["interests"]))
        if "allow_matching" in payload:
            fields.append("allow_matching = ?")
            values.append(int(payload["allow_matching"]))
        fields.append("updated_at = ?")
        values.append(utc_now())
        values.append(profile_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE user_profiles SET {', '.join(fields)} WHERE id = ?", values)
        return self.get_profile(profile_id) or {}

    def delete_profile(self, profile_id: str, anonymous_user_id: str) -> None:
        self.get_owned_profile(profile_id, anonymous_user_id)
        with self.connect() as conn:
            conn.execute("DELETE FROM semantic_cache WHERE owner_profile_id = ? OR candidate_profile_id = ?", (profile_id, profile_id))
            conn.execute("DELETE FROM user_profiles WHERE id = ?", (profile_id,))

    def get_semantic_cache(
        self,
        owner_profile_id: str,
        candidate_profile_id: str,
        criteria_hash: str,
        candidate_hash: str,
        model: str,
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM semantic_cache
                WHERE owner_profile_id = ? AND candidate_profile_id = ?
                  AND criteria_hash = ? AND candidate_hash = ? AND model = ?
                """,
                (owner_profile_id, candidate_profile_id, criteria_hash, candidate_hash, model),
            ).fetchone()
            if not row:
                return None
            return {
                "semantic_score": row["semantic_score"],
                "matched_reasons": _loads(row["matched_reasons_json"], []),
                "unmatched_preferences": _loads(row["unmatched_preferences_json"], []),
                "confidence": row["confidence"],
            }

    def set_semantic_cache(
        self,
        *,
        owner_profile_id: str,
        candidate_profile_id: str,
        criteria_hash: str,
        candidate_hash: str,
        model: str,
        result: Any,
    ) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO semantic_cache (
                    id, owner_profile_id, candidate_profile_id, criteria_hash, candidate_hash,
                    model, semantic_score, matched_reasons_json, unmatched_preferences_json,
                    confidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_profile_id, candidate_profile_id, criteria_hash, candidate_hash, model) DO UPDATE SET
                    semantic_score = excluded.semantic_score,
                    matched_reasons_json = excluded.matched_reasons_json,
                    unmatched_preferences_json = excluded.unmatched_preferences_json,
                    confidence = excluded.confidence,
                    created_at = excluded.created_at
                """,
                (
                    new_uuid(),
                    owner_profile_id,
                    candidate_profile_id,
                    criteria_hash,
                    candidate_hash,
                    model,
                    result.semantic_score,
                    _json(result.matched_reasons),
                    _json(result.unmatched_preferences),
                    result.confidence,
                    now,
                ),
            )

    def write_audit_event(
        self,
        event_type: str,
        status: str,
        model: str | None,
        status_code: int | None,
        error_type: str | None,
        latency_ms: int,
        request_id: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (
                    id, request_id, event_type, status, model, status_code, error_type, latency_ms, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_uuid(),
                    request_id or new_uuid(),
                    event_type,
                    status,
                    model,
                    status_code,
                    error_type,
                    latency_ms,
                    utc_now(),
                ),
            )

    def get_criteria(self, profile_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM match_criteria WHERE profile_id = ?", (profile_id,)).fetchone()
            return criteria_from_row(row) if row else None

    def upsert_criteria(self, profile_id: str, anonymous_user_id: str, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        self.get_owned_profile(profile_id, anonymous_user_id)
        existing = self.get_criteria(profile_id)
        now = utc_now()
        with self.connect() as conn:
            if existing:
                conn.execute(
                    """
                    UPDATE match_criteria
                    SET target_type = ?, location = ?, age_min = ?, age_max = ?, interests_json = ?,
                        required_conditions_json = ?, preferred_conditions_json = ?,
                        free_text_requirement = ?, updated_at = ?
                    WHERE profile_id = ?
                    """,
                    (
                        payload["target_type"],
                        payload.get("location"),
                        payload.get("age_min"),
                        payload.get("age_max"),
                        _json(payload.get("interests", [])),
                        _json(payload.get("required_conditions", {})),
                        _json(payload.get("preferred_conditions", {})),
                        payload.get("free_text_requirement"),
                        now,
                        profile_id,
                    ),
                )
                conn.commit()
                return self.get_criteria(profile_id) or {}, False
            criteria_id = new_uuid()
            conn.execute(
                """
                INSERT INTO match_criteria (
                    id, profile_id, target_type, location, age_min, age_max, interests_json,
                    required_conditions_json, preferred_conditions_json, free_text_requirement,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    criteria_id,
                    profile_id,
                    payload["target_type"],
                    payload.get("location"),
                    payload.get("age_min"),
                    payload.get("age_max"),
                    _json(payload.get("interests", [])),
                    _json(payload.get("required_conditions", {})),
                    _json(payload.get("preferred_conditions", {})),
                    payload.get("free_text_requirement"),
                    now,
                    now,
                ),
            )
            conn.commit()
            return self.get_criteria(profile_id) or {}, True

    def update_criteria(self, profile_id: str, anonymous_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.get_owned_profile(profile_id, anonymous_user_id)
        existing = self.get_criteria(profile_id)
        if not existing:
            raise NotFoundError("Criteria was not found.")
        if not payload:
            return existing
        fields: list[str] = []
        values: list[Any] = []
        for column in ("target_type", "location", "age_min", "age_max", "free_text_requirement"):
            if column in payload:
                fields.append(f"{column} = ?")
                values.append(payload[column])
        json_columns = {
            "interests": "interests_json",
            "required_conditions": "required_conditions_json",
            "preferred_conditions": "preferred_conditions_json",
        }
        for key, column in json_columns.items():
            if key in payload:
                fields.append(f"{column} = ?")
                values.append(_json(payload[key]))
        fields.append("updated_at = ?")
        values.append(utc_now())
        values.append(profile_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE match_criteria SET {', '.join(fields)} WHERE profile_id = ?", values)
        return self.get_criteria(profile_id) or {}

    def list_match_candidates(self, owner_profile_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM user_profiles
                WHERE id != ? AND allow_matching = 1 AND visibility = 'match_pool'
                ORDER BY created_at ASC
                """,
                (owner_profile_id,),
            ).fetchall()
            return [profile_from_row(row) for row in rows]


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        result = super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return result


def profile_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "anonymous_user_id": row["anonymous_user_id"],
        "name": row["name"],
        "age": row["age"],
        "city": row["city"],
        "gender": row["gender"],
        "bio": row["bio"],
        "intent": row["intent"],
        "seeking": row["seeking"],
        "interests": _loads(row["interests_json"], []),
        "image_url": row["image_url"],
        "allow_matching": bool(row["allow_matching"]),
        "visibility": row["visibility"],
        "is_demo": bool(row["is_demo"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def public_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": profile["id"],
        "name": profile["name"],
        "age": profile.get("age"),
        "city": profile.get("city"),
        "gender": profile.get("gender"),
        "bio": profile.get("bio"),
        "intent": profile.get("intent"),
        "seeking": profile.get("seeking"),
        "interests": profile.get("interests", []),
        "image_url": profile.get("image_url"),
        "allow_matching": profile.get("allow_matching", False),
        "visibility": profile.get("visibility", "private"),
        "created_at": profile["created_at"],
        "updated_at": profile["updated_at"],
    }


def criteria_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "profile_id": row["profile_id"],
        "target_type": row["target_type"],
        "location": row["location"],
        "age_min": row["age_min"],
        "age_max": row["age_max"],
        "interests": _loads(row["interests_json"], []),
        "required_conditions": _loads(row["required_conditions_json"], {}),
        "preferred_conditions": _loads(row["preferred_conditions_json"], {}),
        "free_text_requirement": row["free_text_requirement"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_profiles (
    id TEXT PRIMARY KEY,
    anonymous_user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    age INTEGER,
    city TEXT,
    gender TEXT,
    bio TEXT,
    intent TEXT,
    seeking TEXT,
    interests_json TEXT NOT NULL DEFAULT '[]',
    image_url TEXT,
    allow_matching INTEGER NOT NULL DEFAULT 0,
    visibility TEXT NOT NULL DEFAULT 'private',
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profiles_owner
ON user_profiles(anonymous_user_id)
WHERE is_demo = 0;

CREATE INDEX IF NOT EXISTS idx_user_profiles_match_pool
ON user_profiles(allow_matching, visibility);

CREATE TABLE IF NOT EXISTS match_criteria (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL UNIQUE,
    target_type TEXT NOT NULL,
    location TEXT,
    age_min INTEGER,
    age_max INTEGER,
    interests_json TEXT NOT NULL DEFAULT '[]',
    required_conditions_json TEXT NOT NULL DEFAULT '{}',
    preferred_conditions_json TEXT NOT NULL DEFAULT '{}',
    free_text_requirement TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(profile_id) REFERENCES user_profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS semantic_cache (
    id TEXT PRIMARY KEY,
    owner_profile_id TEXT NOT NULL,
    candidate_profile_id TEXT NOT NULL,
    criteria_hash TEXT NOT NULL,
    candidate_hash TEXT NOT NULL,
    model TEXT NOT NULL,
    semantic_score REAL NOT NULL,
    matched_reasons_json TEXT NOT NULL DEFAULT '[]',
    unmatched_preferences_json TEXT NOT NULL DEFAULT '[]',
    confidence TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(owner_profile_id, candidate_profile_id, criteria_hash, candidate_hash, model)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    model TEXT,
    status_code INTEGER,
    error_type TEXT,
    latency_ms INTEGER,
    created_at TEXT NOT NULL
);
"""


DEMO_PROFILES = [
    {
        "id": "11111111-1111-4111-8111-111111111111",
        "anonymous_user_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "name": "Sloane",
        "gender": "Women",
        "age": 29,
        "city": "Brooklyn",
        "bio": "Direct, selective, and not here for vague intentions.",
        "interests": ["verified", "tonight", "chemistry"],
        "intent": "Direct chemistry",
        "seeking": "Everyone",
        "image_url": "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=900&q=82",
    },
    {
        "id": "22222222-2222-4222-8222-222222222222",
        "anonymous_user_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "name": "Nico",
        "gender": "Men",
        "age": 32,
        "city": "Queens",
        "bio": "Clear plans, clean boundaries, no endless small talk.",
        "interests": ["discreet", "consent", "nearby"],
        "intent": "Tonight only",
        "seeking": "Everyone",
        "image_url": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=900&q=82",
    },
    {
        "id": "33333333-3333-4333-8333-333333333333",
        "anonymous_user_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        "name": "Raine",
        "gender": "Women",
        "age": 27,
        "city": "Jersey City",
        "bio": "Flirty first, honest always. I like people who say what they mean.",
        "interests": ["chat first", "playful", "adult only"],
        "intent": "Flirty chat first",
        "seeking": "Everyone",
        "image_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=900&q=82",
    },
    {
        "id": "44444444-4444-4444-8444-444444444444",
        "anonymous_user_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        "name": "Dante",
        "gender": "Men",
        "age": 31,
        "city": "Hoboken",
        "bio": "No pressure, no games, just mutual interest and respect.",
        "interests": ["private", "respectful", "available"],
        "intent": "Open to repeats",
        "seeking": "Everyone",
        "image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=900&q=82",
    },
]
