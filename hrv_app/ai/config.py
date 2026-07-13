from __future__ import annotations

from pathlib import Path

from hrv_app.config import (
    AI_DAILY_BRIEF_LATEST_PATH,
    AI_SSM_BRIEF_LATEST_PATH,
    DATA_DIR,
    FINAL_PATH,
    FINAL_REASON_ITEMS_PATH,
    HRV_AI_API_KEY,
    HRV_AI_BASE_URL,
    HRV_AI_DAILY_ENABLED,
    HRV_AI_ENABLED,
    HRV_AI_LANGUAGE,
    HRV_AI_MAX_TOKENS,
    HRV_AI_MODEL,
    HRV_AI_PROMPT_VERSION,
    HRV_AI_PROVIDER,
    HRV_AI_SSM_ENABLED,
    HRV_AI_SSM_PROMPT_VERSION,
    HRV_AI_TEMPERATURE,
    HRV_AI_THINKING,
    HRV_AI_TIMEOUT_SEC,
    HRV_AI_TOP_P,
    SESSIONS_DAY_PATH,
    SLEEP_PATH,
    SSM_SHADOW_PATH,
)


def _history_dir(kind: str, data_dir: Path | None = None) -> Path:
    base_dir = Path(data_dir) if data_dir is not None else DATA_DIR
    return base_dir / "ai_briefs" / kind


def ai_daily_brief_history_path(date_str: str) -> Path:
    return _history_dir("daily") / f"ENDURANCE_HRV_ai_daily_brief_{date_str}.json"


def ai_ssm_brief_history_path(date_str: str) -> Path:
    return _history_dir("ssm") / f"ENDURANCE_HRV_ai_ssm_brief_{date_str}.json"


def migrate_legacy_ai_brief_history(data_dir: Path | None = None) -> dict[str, int]:
    """Mueve el historial fechado previo fuera de DATA_DIR de forma idempotente."""
    base_dir = Path(data_dir) if data_dir is not None else DATA_DIR
    moved = 0
    conflicts = 0
    errors = 0
    for kind, prefix in (
        ("daily", "ENDURANCE_HRV_ai_daily_brief_"),
        ("ssm", "ENDURANCE_HRV_ai_ssm_brief_"),
    ):
        destination_dir = _history_dir(kind, base_dir)
        for source in base_dir.glob(f"{prefix}*.json"):
            if source.name == f"{prefix}latest.json":
                continue
            destination = destination_dir / source.name
            try:
                if destination.exists():
                    if source.read_bytes() != destination.read_bytes():
                        conflicts += 1
                    else:
                        source.unlink()
                    continue
                destination_dir.mkdir(parents=True, exist_ok=True)
                source.replace(destination)
                moved += 1
            except OSError:
                errors += 1
    return {"moved": moved, "conflicts": conflicts, "errors": errors}


def ai_chat_completions_url() -> str:
    base = HRV_AI_BASE_URL.rstrip("/")
    if not base:
        return ""
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


__all__ = [
    "AI_DAILY_BRIEF_LATEST_PATH",
    "AI_SSM_BRIEF_LATEST_PATH",
    "FINAL_PATH",
    "FINAL_REASON_ITEMS_PATH",
    "HRV_AI_API_KEY",
    "HRV_AI_DAILY_ENABLED",
    "HRV_AI_ENABLED",
    "HRV_AI_LANGUAGE",
    "HRV_AI_MAX_TOKENS",
    "HRV_AI_MODEL",
    "HRV_AI_PROMPT_VERSION",
    "HRV_AI_PROVIDER",
    "HRV_AI_SSM_ENABLED",
    "HRV_AI_SSM_PROMPT_VERSION",
    "HRV_AI_TEMPERATURE",
    "HRV_AI_THINKING",
    "HRV_AI_TIMEOUT_SEC",
    "HRV_AI_TOP_P",
    "SESSIONS_DAY_PATH",
    "SLEEP_PATH",
    "SSM_SHADOW_PATH",
    "ai_chat_completions_url",
    "ai_daily_brief_history_path",
    "ai_ssm_brief_history_path",
    "migrate_legacy_ai_brief_history",
]
