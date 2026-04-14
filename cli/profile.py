from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cli.models import AnalystType, normalize_analyst_type, serialize_analyst_type
from tradingagents.storage import SQLiteRepository
from tradingagents.time_utils import (
    current_analysis_time,
    format_time_for_path,
    normalize_timeframe,
    resolve_analysis_time,
)

PROFILE_FILENAME = "tradingagents.defaults.json"
DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent.parent / PROFILE_FILENAME
DEFAULT_ANALYSTS = [
    AnalystType.MARKET,
    AnalystType.VOLUME_FLOW,
    AnalystType.FUNDING_OI,
    AnalystType.NEWS,
    AnalystType.TOKENOMICS,
]
VALID_RESEARCH_DEPTHS = {1, 3, 5}
DEFAULT_TIMEFRAME = "1h"
TEXT_ENCODING = "utf-8"


def get_today_analysis_date(timeframe: str = DEFAULT_TIMEFRAME) -> str:
    return current_analysis_time(timeframe=timeframe)


def resolve_profile_path(profile_path: str | Path | None = None) -> Path:
    if profile_path is None:
        return DEFAULT_PROFILE_PATH
    return Path(profile_path).expanduser().resolve()


def resolve_profile_key(profile_path: str | Path | None = None) -> str:
    return str(resolve_profile_path(profile_path))


def get_profile_repository() -> SQLiteRepository:
    return SQLiteRepository()


def default_profile_payload() -> dict[str, Any]:
    return {
        "asset_symbol": "BTC-PERP",
        "timeframe": DEFAULT_TIMEFRAME,
        "analysis_date": "now",
        "storage_retention_days": 7,
        "storage_max_runs_per_asset_timeframe": 240,
        "storage_max_reflection_entries_per_memory": 300,
        "output_language": "English",
        "analysts": [serialize_analyst_type(analyst) for analyst in DEFAULT_ANALYSTS],
        "research_depth": 1,
        "llm_provider": "codex_exec",
        "backend_url": None,
        "shallow_thinker": "gpt-5.4-mini",
        "deep_thinker": "gpt-5.4",
        "google_thinking_level": None,
        "openai_reasoning_effort": None,
        "anthropic_effort": None,
    }


def load_profile(profile_path: str | Path | None = None) -> dict[str, Any] | None:
    path = resolve_profile_path(profile_path)
    repository = get_profile_repository()
    profile_key = resolve_profile_key(path)
    stored_profile = repository.get_profile(profile_key)
    if stored_profile is not None:
        return stored_profile
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding=TEXT_ENCODING))
    if not isinstance(payload, dict):
        raise ValueError(f"Profile JSON must contain an object: {path}")
    repository.upsert_profile(profile_key, payload, source_path=str(path))
    return payload


def save_profile(
    selections: dict[str, Any],
    profile_path: str | Path | None = None,
    analysis_date_value: str = "now",
    existing_profile: dict[str, Any] | None = None,
) -> Path:
    path = resolve_profile_path(profile_path)
    asset_symbol = str(selections["asset_symbol"]).strip().upper()
    payload = {
        "asset_symbol": asset_symbol,
        "timeframe": _normalize_timeframe_value(selections.get("timeframe")),
        "analysis_date": analysis_date_value,
        "storage_retention_days": existing_profile.get("storage_retention_days", 7)
        if existing_profile
        else 7,
        "storage_max_runs_per_asset_timeframe": existing_profile.get(
            "storage_max_runs_per_asset_timeframe", 240
        )
        if existing_profile
        else 240,
        "storage_max_reflection_entries_per_memory": existing_profile.get(
            "storage_max_reflection_entries_per_memory", 300
        )
        if existing_profile
        else 300,
        "output_language": selections.get("output_language") or "English",
        "analysts": [
            serialize_analyst_type(analyst)
            for analyst in selections.get("analysts", DEFAULT_ANALYSTS)
        ],
        "research_depth": selections.get("research_depth", 1),
        "llm_provider": str(selections.get("llm_provider") or "codex_exec").lower(),
        "backend_url": selections.get("backend_url"),
        "shallow_thinker": selections.get("shallow_thinker"),
        "deep_thinker": selections.get("deep_thinker"),
        "google_thinking_level": selections.get("google_thinking_level"),
        "openai_reasoning_effort": selections.get("openai_reasoning_effort"),
        "anthropic_effort": selections.get("anthropic_effort"),
    }
    repository = get_profile_repository()
    repository.upsert_profile(
        resolve_profile_key(path),
        payload,
        source_path=str(path),
    )
    return repository.db_path


def normalize_profile(raw_profile: dict[str, Any] | None) -> dict[str, Any]:
    profile = default_profile_payload()
    if not raw_profile:
        return profile

    asset_symbol = str(raw_profile.get("asset_symbol") or profile["asset_symbol"]).strip().upper()
    profile["asset_symbol"] = asset_symbol or profile["asset_symbol"]

    profile["timeframe"] = _normalize_timeframe_value(raw_profile.get("timeframe"))

    raw_date = raw_profile.get("analysis_date", profile["analysis_date"])
    if raw_date is None:
        profile["analysis_date"] = "now"
    else:
        profile["analysis_date"] = str(raw_date).strip() or "now"

    try:
        storage_retention_days = int(
            raw_profile.get("storage_retention_days", profile["storage_retention_days"])
        )
    except (TypeError, ValueError):
        storage_retention_days = profile["storage_retention_days"]
    profile["storage_retention_days"] = max(1, storage_retention_days)

    try:
        storage_max_runs = int(
            raw_profile.get(
                "storage_max_runs_per_asset_timeframe",
                profile["storage_max_runs_per_asset_timeframe"],
            )
        )
    except (TypeError, ValueError):
        storage_max_runs = profile["storage_max_runs_per_asset_timeframe"]
    profile["storage_max_runs_per_asset_timeframe"] = max(1, storage_max_runs)

    try:
        storage_max_memory_entries = int(
            raw_profile.get(
                "storage_max_reflection_entries_per_memory",
                profile["storage_max_reflection_entries_per_memory"],
            )
        )
    except (TypeError, ValueError):
        storage_max_memory_entries = profile[
            "storage_max_reflection_entries_per_memory"
        ]
    profile["storage_max_reflection_entries_per_memory"] = max(
        1, storage_max_memory_entries
    )

    raw_analysts = raw_profile.get("analysts", profile["analysts"])
    normalized_analysts = _normalize_analysts(raw_analysts)
    profile["analysts"] = [analyst.value for analyst in normalized_analysts]

    depth = raw_profile.get("research_depth", profile["research_depth"])
    profile["research_depth"] = depth if depth in VALID_RESEARCH_DEPTHS else 1

    llm_provider = str(raw_profile.get("llm_provider") or profile["llm_provider"]).strip().lower()
    profile["llm_provider"] = llm_provider or profile["llm_provider"]

    profile["backend_url"] = raw_profile.get("backend_url")
    profile["shallow_thinker"] = raw_profile.get("shallow_thinker") or profile["shallow_thinker"]
    profile["deep_thinker"] = raw_profile.get("deep_thinker") or profile["deep_thinker"]
    profile["google_thinking_level"] = raw_profile.get("google_thinking_level")
    profile["openai_reasoning_effort"] = raw_profile.get("openai_reasoning_effort")
    profile["anthropic_effort"] = raw_profile.get("anthropic_effort")
    profile["output_language"] = raw_profile.get("output_language") or profile["output_language"]
    return profile


def build_selections_from_profile(raw_profile: dict[str, Any] | None) -> dict[str, Any]:
    profile = normalize_profile(raw_profile)
    timeframe = profile["timeframe"]
    return {
        "asset_symbol": profile["asset_symbol"],
        "timeframe": timeframe,
        "analysis_date": resolve_analysis_date(profile.get("analysis_date"), timeframe=timeframe),
        "analysts": _normalize_analysts(profile.get("analysts")),
        "research_depth": profile["research_depth"],
        "storage_retention_days": profile["storage_retention_days"],
        "storage_max_runs_per_asset_timeframe": profile[
            "storage_max_runs_per_asset_timeframe"
        ],
        "storage_max_reflection_entries_per_memory": profile[
            "storage_max_reflection_entries_per_memory"
        ],
        "llm_provider": profile["llm_provider"],
        "backend_url": profile.get("backend_url"),
        "shallow_thinker": profile["shallow_thinker"],
        "deep_thinker": profile["deep_thinker"],
        "google_thinking_level": profile.get("google_thinking_level"),
        "openai_reasoning_effort": profile.get("openai_reasoning_effort"),
        "anthropic_effort": profile.get("anthropic_effort"),
        "output_language": profile.get("output_language", "English"),
    }


def profile_summary(selections: dict[str, Any]) -> str:
    analysts = ", ".join(analyst.value for analyst in selections["analysts"])
    return (
        f"asset={selections['asset_symbol']} | "
        f"timeframe={selections['timeframe']} | "
        f"time={selections['analysis_date']} | "
        f"provider={selections['llm_provider']} | quick={selections['shallow_thinker']} | "
        f"deep={selections['deep_thinker']} | depth={selections['research_depth']} | "
        f"analysts={analysts}"
    )


def resolve_analysis_date(value: Any, timeframe: str = DEFAULT_TIMEFRAME) -> str:
    return resolve_analysis_time(value, timeframe=timeframe)


def format_analysis_date_for_path(value: Any, timeframe: str = DEFAULT_TIMEFRAME) -> str:
    return format_time_for_path(value, timeframe=timeframe)


def _normalize_analysts(raw_analysts: Any) -> list[AnalystType]:
    if not isinstance(raw_analysts, list):
        return DEFAULT_ANALYSTS.copy()

    normalized: list[AnalystType] = []
    for value in raw_analysts:
        try:
            analyst = normalize_analyst_type(value)
        except ValueError:
            continue
        if analyst not in normalized:
            normalized.append(analyst)

    return normalized or DEFAULT_ANALYSTS.copy()


def _normalize_timeframe_value(value: Any) -> str:
    try:
        return normalize_timeframe(str(value or DEFAULT_TIMEFRAME))
    except ValueError:
        return DEFAULT_TIMEFRAME
