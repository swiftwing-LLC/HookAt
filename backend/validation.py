from __future__ import annotations

import json
import re
import uuid
from typing import Any

from .errors import UnauthorizedError, ValidationError


CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
DANGEROUS_TEXT = re.compile(r"<|>|javascript:", re.IGNORECASE)
TARGET_TYPES = {"Women", "Men", "Other", "Everyone"}
INTENTS = {"Direct chemistry", "Flirty chat first", "Tonight only", "Open to repeats"}


def require_uuid(value: str | None, field: str) -> str:
    if not value:
        raise ValidationError(f"{field} is required.", details={"field": field})
    try:
        parsed = uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be a valid UUID.", details={"field": field}) from exc
    return str(parsed)


def require_anonymous_user_id(headers: dict[str, str]) -> str:
    value = headers.get("x-anonymous-user-id") or headers.get("X-Anonymous-User-Id")
    if not value:
        raise UnauthorizedError("X-Anonymous-User-Id header is required.")
    return require_uuid(value, "anonymous_user_id")


def parse_json_body(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("Request body must be valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ValidationError("Request JSON must be an object.")
    return parsed


def clean_text(
    value: Any,
    field: str,
    *,
    required: bool = False,
    max_length: int = 255,
    allow_newlines: bool = False,
    reject_markup: bool = True,
) -> str | None:
    if value is None:
        if required:
            raise ValidationError(f"{field} is required.", details={"field": field})
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string.", details={"field": field})

    text = value.strip()
    if required and not text:
        raise ValidationError(f"{field} cannot be empty.", details={"field": field})
    if not text:
        return None
    if len(text) > max_length:
        raise ValidationError(f"{field} must be {max_length} characters or fewer.", details={"field": field})
    if CONTROL_CHARS.search(text):
        raise ValidationError(f"{field} contains unsupported control characters.", details={"field": field})
    if not allow_newlines and ("\n" in text or "\r" in text):
        raise ValidationError(f"{field} cannot contain line breaks.", details={"field": field})
    if reject_markup and DANGEROUS_TEXT.search(text):
        raise ValidationError(f"{field} contains unsupported characters.", details={"field": field})
    return text


def clean_name(value: Any) -> str:
    return clean_text(value, "name", required=True, max_length=100, reject_markup=True) or ""


def clean_age(value: Any, field: str = "age") -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be an integer.", details={"field": field})
    try:
        age = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be an integer.", details={"field": field}) from exc
    if age < 18 or age > 99:
        raise ValidationError(f"{field} must be between 18 and 99.", details={"field": field})
    return age


def clean_target_type(value: Any) -> str:
    target_type = clean_text(value, "target_type", required=True, max_length=40)
    if target_type not in TARGET_TYPES:
        raise ValidationError("target_type is not supported.", details={"field": "target_type"})
    return target_type


def clean_intent(value: Any) -> str | None:
    intent = clean_text(value, "intent", required=False, max_length=80)
    if intent and intent not in INTENTS:
        raise ValidationError("intent is not supported.", details={"field": "intent"})
    return intent


def clean_bool(value: Any, field: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValidationError(f"{field} must be a boolean.", details={"field": field})


def clean_interests(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError("interests must be an array.", details={"field": "interests"})
    if len(value) > 20:
        raise ValidationError("interests cannot contain more than 20 items.", details={"field": "interests"})
    cleaned: list[str] = []
    for item in value:
        text = clean_text(item, "interests", required=True, max_length=40)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def clean_json_object(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be an object.", details={"field": field})
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(encoded) > 4096:
        raise ValidationError(f"{field} is too large.", details={"field": field})
    _validate_json_leaf(value, field)
    return value


def _validate_json_leaf(value: Any, field: str) -> None:
    if isinstance(value, dict):
        if len(value) > 50:
            raise ValidationError(f"{field} has too many entries.", details={"field": field})
        for key, child in value.items():
            clean_text(str(key), field, required=True, max_length=80)
            _validate_json_leaf(child, field)
    elif isinstance(value, list):
        if len(value) > 50:
            raise ValidationError(f"{field} has too many items.", details={"field": field})
        for child in value:
            _validate_json_leaf(child, field)
    elif isinstance(value, str):
        clean_text(value, field, required=False, max_length=500, allow_newlines=True)
    elif value is None or isinstance(value, (bool, int, float)):
        return
    else:
        raise ValidationError(f"{field} contains an unsupported value.", details={"field": field})


def validate_age_range(age_min: Any, age_max: Any) -> tuple[int | None, int | None]:
    minimum = clean_age(age_min, "age_min") if age_min is not None else None
    maximum = clean_age(age_max, "age_max") if age_max is not None else None
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValidationError("age_min cannot be greater than age_max.", details={"field": "age_min"})
    return minimum, maximum

