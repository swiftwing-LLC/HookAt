from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT_DIR / ".env")


def _csv_env(name: str, default: str) -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(slots=True)
class Config:
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'hookat.db'}")
    )
    demo_storage_mode: str = field(default_factory=lambda: os.getenv("DEMO_STORAGE_MODE", "database"))
    frontend_origins: list[str] = field(
        default_factory=lambda: _csv_env("FRONTEND_ORIGIN", "http://localhost:8000,http://127.0.0.1:8000")
    )
    max_body_bytes: int = field(default_factory=lambda: _int_env("MAX_BODY_BYTES", 65536))
    rate_limit_requests: int = field(default_factory=lambda: _int_env("RATE_LIMIT_REQUESTS_PER_MINUTE", 120))
    ai_rate_limit_requests: int = field(default_factory=lambda: _int_env("AI_RATE_LIMIT_REQUESTS_PER_MINUTE", 30))
    structured_weight: float = field(default_factory=lambda: _float_env("MATCHING_STRUCTURED_WEIGHT", 0.7))
    semantic_weight: float = field(default_factory=lambda: _float_env("MATCHING_SEMANTIC_WEIGHT", 0.3))
    deepseek_api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    deepseek_base_url: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    )
    deepseek_model: str = field(default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
    deepseek_timeout_seconds: float = field(default_factory=lambda: _float_env("DEEPSEEK_TIMEOUT_SECONDS", 8.0))
    deepseek_retries: int = field(default_factory=lambda: _int_env("DEEPSEEK_RETRIES", 1))
    deepseek_concurrency: int = field(default_factory=lambda: _int_env("DEEPSEEK_CONCURRENCY_LIMIT", 2))
    static_dir: Path = field(default_factory=lambda: BASE_DIR.parent / "002")

    def database_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("This MVP backend supports sqlite:/// DATABASE_URL values.")
        path = self.database_url.removeprefix("sqlite:///")
        return Path(path).expanduser().resolve()

    def normalized_storage_mode(self) -> str:
        mode = self.demo_storage_mode.lower().strip()
        return mode if mode in {"local", "database"} else "database"
