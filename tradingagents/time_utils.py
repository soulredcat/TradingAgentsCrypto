from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


ANALYSIS_DATETIME_FORMAT = "%Y-%m-%d %H:%M"
ANALYSIS_DATE_FORMAT = "%Y-%m-%d"
_DATETIME_FORMAT_CANDIDATES = (
    ANALYSIS_DATETIME_FORMAT,
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H:%M:%S",
    ANALYSIS_DATE_FORMAT,
)
_RELATIVE_ALIASES = {"today", "now", "current"}
VALID_TIMEFRAMES = ("1h", "4h", "1d")
_TIMEFRAME_TO_DELTA = {
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


def current_analysis_time(now: datetime | None = None, timeframe: str = "1h") -> str:
    normalized_timeframe = normalize_timeframe(timeframe)
    return _format_analysis_time(
        _normalize_to_timeframe(now or datetime.now(), normalized_timeframe),
        normalized_timeframe,
    )


def parse_analysis_time(value: Any, timeframe: str = "1h") -> datetime:
    normalized_timeframe = normalize_timeframe(timeframe)
    if isinstance(value, datetime):
        return _normalize_to_timeframe(value, normalized_timeframe)

    text = str(value or "").strip()
    if not text:
        return _normalize_to_timeframe(datetime.now(), normalized_timeframe)
    if text.lower() in _RELATIVE_ALIASES:
        return _normalize_to_timeframe(datetime.now(), normalized_timeframe)

    for candidate in _DATETIME_FORMAT_CANDIDATES:
        try:
            parsed = datetime.strptime(text, candidate)
            return _normalize_to_timeframe(parsed, normalized_timeframe)
        except ValueError:
            continue

    raise ValueError(
        "Invalid analysis time. Use 'now' or a timestamp like YYYY-MM-DD HH:MM."
    )


def resolve_analysis_time(value: Any, timeframe: str = "1h") -> str:
    normalized_timeframe = normalize_timeframe(timeframe)
    return _format_analysis_time(parse_analysis_time(value, normalized_timeframe), normalized_timeframe)


def timeframe_to_timedelta(timeframe: str) -> timedelta:
    return _TIMEFRAME_TO_DELTA[normalize_timeframe(timeframe)]


def normalize_timeframe(timeframe: str | None) -> str:
    normalized = str(timeframe or "1h").strip().lower()
    if normalized not in VALID_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe '{timeframe}'.")
    return normalized


def format_time_for_path(value: Any, timeframe: str = "1h") -> str:
    return resolve_analysis_time(value, timeframe=timeframe).replace(":", "-").replace(" ", "_")


def format_series_timestamp(value: datetime, timeframe: str) -> str:
    normalized = normalize_timeframe(timeframe)
    if normalized.endswith("d"):
        return value.strftime(ANALYSIS_DATE_FORMAT)
    return value.strftime(ANALYSIS_DATETIME_FORMAT)


def _format_analysis_time(value: datetime, timeframe: str) -> str:
    if normalize_timeframe(timeframe) == "1d":
        return value.strftime(ANALYSIS_DATE_FORMAT)
    return value.strftime(ANALYSIS_DATETIME_FORMAT)


def _normalize_to_timeframe(value: datetime, timeframe: str) -> datetime:
    normalized = normalize_timeframe(timeframe)
    if normalized == "1d":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    if normalized == "4h":
        aligned_hour = value.hour - (value.hour % 4)
        return value.replace(hour=aligned_hour, minute=0, second=0, microsecond=0)
    return value.replace(minute=0, second=0, microsecond=0)
