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


def ai_daily_brief_history_path(date_str: str) -> Path:
    return DATA_DIR / f"ENDURANCE_HRV_ai_daily_brief_{date_str}.json"


def ai_ssm_brief_history_path(date_str: str) -> Path:
    return DATA_DIR / f"ENDURANCE_HRV_ai_ssm_brief_{date_str}.json"


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
]
