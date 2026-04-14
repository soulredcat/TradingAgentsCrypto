from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from cli.models import AnalystType

PROFILE_FILENAME = "tradingagents.defaults.json"
DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent.parent / PROFILE_FILENAME
DEFAULT_ANALYSTS = [
    AnalystType.MARKET,
    AnalystType.SENTIMENT,
    AnalystType.NEWS,
    AnalystType.TOKENOMICS,
]
VALID_RESEARCH_DEPTHS = {1, 3, 5}
TEXT_ENCODING = "utf-8"


def get_today_analysis_date() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")


def resolve_profile_path(profile_path: str | Path | None = None) -> Path:
    if profile_path is None:
        return DEFAULT_PROFILE_PATH
    return Path(profile_path).expanduser().resolve()


def default_profile_payload() -> dict[str, Any]:
    return {
        "asset_symbol": "BTCUSDT",
        "analysis_date": "today",
        "output_language": "English",
        "analysts": [analyst.value for analyst in DEFAULT_ANALYSTS],
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
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding=TEXT_ENCODING))
    if not isinstance(payload, dict):
        raise ValueError(f"Profile JSON must contain an object: {path}")
    return payload


def save_profile(
    selections: dict[str, Any],
    profile_path: str | Path | None = None,
    analysis_date_value: str = "today",
) -> Path:
    path = resolve_profile_path(profile_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "asset_symbol": str(selections["asset_symbol"]).strip().upper(),
        "analysis_date": analysis_date_value,
        "output_language": selections.get("output_language") or "English",
        "analysts": [analyst.value for analyst in selections.get("analysts", DEFAULT_ANALYSTS)],
        "research_depth": selections.get("research_depth", 1),
        "llm_provider": str(selections.get("llm_provider") or "codex_exec").lower(),
        "backend_url": selections.get("backend_url"),
        "shallow_thinker": selections.get("shallow_thinker"),
        "deep_thinker": selections.get("deep_thinker"),
        "google_thinking_level": selections.get("google_thinking_level"),
        "openai_reasoning_effort": selections.get("openai_reasoning_effort"),
        "anthropic_effort": selections.get("anthropic_effort"),
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding=TEXT_ENCODING,
    )
    return path


def normalize_profile(raw_profile: dict[str, Any] | None) -> dict[str, Any]:
    profile = default_profile_payload()
    if not raw_profile:
        return profile

    asset_symbol = str(raw_profile.get("asset_symbol") or profile["asset_symbol"]).strip().upper()
    profile["asset_symbol"] = asset_symbol or profile["asset_symbol"]

    raw_date = raw_profile.get("analysis_date", profile["analysis_date"])
    if raw_date is None:
        profile["analysis_date"] = "today"
    else:
        profile["analysis_date"] = str(raw_date).strip() or "today"

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
    return {
        "asset_symbol": profile["asset_symbol"],
        "analysis_date": resolve_analysis_date(profile.get("analysis_date")),
        "analysts": _normalize_analysts(profile.get("analysts")),
        "research_depth": profile["research_depth"],
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
        f"asset={selections['asset_symbol']} | date={selections['analysis_date']} | "
        f"provider={selections['llm_provider']} | quick={selections['shallow_thinker']} | "
        f"deep={selections['deep_thinker']} | depth={selections['research_depth']} | "
        f"analysts={analysts}"
    )


def resolve_analysis_date(value: Any) -> str:
    if value is None:
        return get_today_analysis_date()

    text = str(value).strip()
    if not text or text.lower() in {"today", "now", "current"}:
        return get_today_analysis_date()
    return text


def _normalize_analysts(raw_analysts: Any) -> list[AnalystType]:
    if not isinstance(raw_analysts, list):
        return DEFAULT_ANALYSTS.copy()

    normalized: list[AnalystType] = []
    for value in raw_analysts:
        try:
            analyst = AnalystType(str(value).strip().lower())
        except ValueError:
            continue
        if analyst not in normalized:
            normalized.append(analyst)

    return normalized or DEFAULT_ANALYSTS.copy()
