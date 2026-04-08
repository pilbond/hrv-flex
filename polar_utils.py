from __future__ import annotations

import os
from typing import Any


def get_field_variant(payload: dict[str, Any], *keys: str, default=None):
    """Return the first non-None value across key variants."""
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return default


def parse_float(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "n/a"}:
        return None
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_duration_to_minutes(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None
    if not text.startswith("PT"):
        return parse_float(text)

    text = text[2:]
    total_seconds = 0.0
    number = ""
    for ch in text:
        if ch.isdigit() or ch == ".":
            number += ch
            continue
        if not number:
            continue
        value_num = float(number)
        if ch == "H":
            total_seconds += value_num * 3600.0
        elif ch == "M":
            total_seconds += value_num * 60.0
        elif ch == "S":
            total_seconds += value_num
        number = ""
    return total_seconds / 60.0 if total_seconds > 0 else None


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value == "":
        return default
    return value in {"1", "true", "yes", "on"}


def response_excerpt(response: Any, limit: int = 300) -> str:
    text = (getattr(response, "text", "") or "").strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "..."
    return text
