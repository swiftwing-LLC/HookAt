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
