from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Tuple

import pandas as pd
import requests
from stockstats import wrap

from .crypto_common import extract_base_asset, requests_verify_ssl
from tradingagents.dataflows.config import get_config
from tradingagents.time_utils import (
    format_series_timestamp,
    parse_analysis_time,
    resolve_analysis_time,
    timeframe_to_timedelta,
)


HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"

_HYPERLIQUID_SYMBOL_ALIASES = {
    "BONK": "kBONK",
    "DOGS": "kDOGS",
    "FLOKI": "kFLOKI",
    "LUNC": "kLUNC",
    "PEPE": "kPEPE",
    "SHIB": "kSHIB",
}

_INDICATOR_DESCRIPTIONS: Dict[str, str] = {
    "close_20_sma": (
        "20 SMA: Short-to-medium trend baseline for crypto swing structure. "
        "Usage: judge local trend, dynamic support/resistance, and trend continuation."
    ),
    "close_50_sma": (
        "50 SMA: Mid-cycle trend benchmark. "
        "Usage: track directional bias and identify trend failure after breakdowns."
    ),
    "close_200_sma": (
        "200 SMA: High-level trend regime filter. "
        "Usage: separate structural bull trends from bear-market rallies."
    ),
    "close_10_ema": (
        "10 EMA: Fast trend response for volatile crypto markets. "
        "Usage: spot momentum acceleration and short-term continuation entries."
    ),
    "macd": (
        "MACD: Momentum and trend-strength measure via EMA spread. "
        "Usage: confirm breakouts, trend continuation, and momentum loss."
    ),
    "macds": (
        "MACD Signal: Smoothed MACD line. "
        "Usage: track crossover-based momentum shifts."
    ),
    "macdh": (
        "MACD Histogram: Distance between MACD and signal lines. "
        "Usage: gauge acceleration or deceleration in crypto trend strength."
    ),
    "rsi": (
        "RSI: Momentum oscillator for overbought/oversold conditions. "
        "Usage: identify exhaustion, divergence, and trend continuation pullbacks."
    ),
    "boll": (
        "Bollinger Midline: Mean-reversion anchor. "
        "Usage: evaluate whether price is reverting or trending away from fair value."
    ),
    "boll_ub": (
        "Bollinger Upper Band: Upper volatility envelope. "
        "Usage: identify expansion, breakout continuation, or local exhaustion."
    ),
    "boll_lb": (
        "Bollinger Lower Band: Lower volatility envelope. "
        "Usage: identify downside expansion, mean-reversion zones, or breakdown risk."
    ),
    "atr": (
        "ATR: Volatility and risk sizing metric. "
        "Usage: calibrate stop placement and position sizing for crypto swings."
    ),
    "vwma": (
        "VWMA: Volume-weighted moving average. "
        "Usage: confirm whether price trend is supported by real participation."
    ),
    "mfi": (
        "MFI: Volume-adjusted momentum. "
        "Usage: detect buying/selling pressure imbalance and divergence."
    ),
}


def _post_info(payload: Dict[str, Any]) -> Any:
    response = requests.post(
        HYPERLIQUID_INFO_URL,
        json=payload,
        timeout=20,
        headers={"Accept": "application/json"},
        verify=requests_verify_ssl(),
    )
    response.raise_for_status()
    return response.json()


@lru_cache(maxsize=1)
def _get_meta_and_asset_contexts() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    response = _post_info({"type": "metaAndAssetCtxs"})
    if not isinstance(response, list) or len(response) != 2:
        raise ValueError("Unexpected Hyperliquid metaAndAssetCtxs response shape.")
    universe, contexts = response
    if not isinstance(universe, dict) or not isinstance(contexts, list):
        raise ValueError("Unexpected Hyperliquid asset metadata payload.")
    raw_universe = universe.get("universe", [])
    if not isinstance(raw_universe, list):
        raise ValueError("Hyperliquid universe payload missing.")
    return raw_universe, contexts


def _resolve_hyperliquid_coin(asset_symbol: str) -> str:
    base_asset = extract_base_asset(asset_symbol)
    candidates = [base_asset]
    aliased = _HYPERLIQUID_SYMBOL_ALIASES.get(base_asset)
    if aliased and aliased not in candidates:
        candidates.append(aliased)

    universe, _ = _get_meta_and_asset_contexts()
    available = {str(item.get("name", "")).upper() for item in universe}
    for candidate in candidates:
        if candidate.upper() in available:
            return candidate.upper()

    raise ValueError(f"Hyperliquid does not list perpetual market '{base_asset}'.")


def _timeframe() -> str:
    return str(get_config().get("timeframe", "1h")).lower()


def _timeframe_delta() -> timedelta:
    return timeframe_to_timedelta(_timeframe())


def _fetch_candles(coin: str, start_ms: int, end_ms: int, interval: str | None = None) -> pd.DataFrame:
    rows = _post_info(
        {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": interval or _timeframe(),
                "startTime": start_ms,
                "endTime": end_ms,
            },
        }
    )
    if not isinstance(rows, list) or not rows:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])

    data = pd.DataFrame(rows)
    for required in ("t", "o", "h", "l", "c", "v"):
        if required not in data.columns:
            raise ValueError("Unexpected Hyperliquid candle response shape.")

    data["Date"] = pd.to_datetime(data["t"], unit="ms")
    data["Open"] = pd.to_numeric(data["o"], errors="coerce")
    data["High"] = pd.to_numeric(data["h"], errors="coerce")
    data["Low"] = pd.to_numeric(data["l"], errors="coerce")
    data["Close"] = pd.to_numeric(data["c"], errors="coerce")
    data["Volume"] = pd.to_numeric(data["v"], errors="coerce")
    return data[["Date", "Open", "High", "Low", "Close", "Volume"]].dropna()


def load_ohlcv(asset_symbol: str, curr_date: str, history_days: int = 420) -> pd.DataFrame:
    """Load Hyperliquid perpetual OHLCV without look-ahead bias."""
    coin = _resolve_hyperliquid_coin(asset_symbol)
    timeframe = _timeframe()
    curr_date_dt = pd.Timestamp(parse_analysis_time(curr_date, timeframe=timeframe))
    start_dt = curr_date_dt - timedelta(days=history_days)
    end_dt = curr_date_dt + _timeframe_delta()
    data = _fetch_candles(
        coin,
        int(start_dt.timestamp() * 1000),
        int(end_dt.timestamp() * 1000),
    )
    return data[data["Date"] <= curr_date_dt]


def get_market_data(asset_symbol: str, start_date: str, end_date: str) -> str:
    """Return Hyperliquid perpetual OHLCV data for a coin."""
    timeframe = _timeframe()
    try:
        coin = _resolve_hyperliquid_coin(asset_symbol)
        start_dt = parse_analysis_time(start_date, timeframe=timeframe)
        end_dt = parse_analysis_time(end_date, timeframe=timeframe) + _timeframe_delta()
        data = _fetch_candles(
            coin,
            int(start_dt.timestamp() * 1000),
            int(end_dt.timestamp() * 1000),
        )
    except (ValueError, requests.RequestException) as exc:
        return f"Hyperliquid market data unavailable for {asset_symbol}: {exc}"

    if data.empty:
        return f"No Hyperliquid market data found for '{coin}' between {start_date} and {end_date}."

    formatted = data.copy()
    formatted["Date"] = formatted["Date"].apply(lambda value: format_series_timestamp(value, timeframe))
    csv_string = formatted.to_csv(index=False)
    header = (
        f"# Hyperliquid perpetual market data for {coin} from {resolve_analysis_time(start_date, timeframe=timeframe)} "
        f"to {resolve_analysis_time(end_date, timeframe=timeframe)}\n"
    )
    header += f"# Timeframe: {timeframe}\n"
    header += f"# Records: {len(data)}\n"
    header += f"# Retrieved at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
    return header + csv_string


def get_indicator_window(asset_symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
    """Calculate indicator values from Hyperliquid perpetual OHLCV."""
    indicator = indicator.strip().lower()
    if indicator not in _INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"Indicator '{indicator}' is not supported. Choose from: {sorted(_INDICATOR_DESCRIPTIONS)}"
        )

    try:
        coin = _resolve_hyperliquid_coin(asset_symbol)
        data = load_ohlcv(asset_symbol, curr_date, history_days=max(420, look_back_days + 220))
    except (ValueError, requests.RequestException) as exc:
        return f"Hyperliquid indicator data unavailable for {asset_symbol}: {exc}"

    if data.empty:
        return f"No Hyperliquid OHLCV data available for '{asset_symbol}' to compute {indicator}."

    wrapped = wrap(data.copy())
    timeframe = _timeframe()
    step = _timeframe_delta()
    wrapped["Date"] = wrapped["Date"].apply(lambda value: format_series_timestamp(value, timeframe))
    wrapped[indicator]

    values_by_date = {}
    for _, row in wrapped.iterrows():
        date_key = row["Date"]
        value = row[indicator]
        values_by_date[date_key] = "N/A" if pd.isna(value) else str(value)

    curr_date_dt = parse_analysis_time(curr_date, timeframe=timeframe)
    start_dt = curr_date_dt - timedelta(days=look_back_days)
    lines: List[str] = []
    cursor = curr_date_dt
    max_points = 96 if step < timedelta(days=1) else look_back_days + 1
    points = 0
    while cursor >= start_dt and points < max_points:
        date_key = format_series_timestamp(cursor, timeframe)
        lines.append(f"{date_key}: {values_by_date.get(date_key, 'N/A')}")
        cursor -= step
        points += 1

    truncation_note = ""
    if cursor >= start_dt:
        truncation_note = f"\n\nWindow truncated to the latest {max_points} {timeframe} periods for readability."
    return (
        f"## {indicator} values for Hyperliquid {coin} from {format_series_timestamp(start_dt, timeframe)} "
        f"to {resolve_analysis_time(curr_date, timeframe=timeframe)}\n\n"
        + "\n".join(lines)
        + "\n\n"
        + _INDICATOR_DESCRIPTIONS[indicator]
        + truncation_note
    )


def get_derivatives_metrics(asset_symbol: str, curr_date: str, look_back_days: int = 7) -> str:
    """Fetch Hyperliquid funding history and avoid look-ahead bias on open interest."""
    funding_lines: List[str] = []
    coin = extract_base_asset(asset_symbol)
    timeframe = _timeframe()
    try:
        coin = _resolve_hyperliquid_coin(asset_symbol)
        end_dt = parse_analysis_time(curr_date, timeframe=timeframe) + _timeframe_delta()
        start_dt = end_dt - timedelta(days=look_back_days)
        raw_funding = _post_info(
            {
                "type": "fundingHistory",
                "coin": coin,
                "startTime": int(start_dt.timestamp() * 1000),
                "endTime": int(end_dt.timestamp() * 1000),
            }
        )
    except (ValueError, requests.RequestException) as exc:
        raw_funding = [{"error": f"Funding data unavailable: {exc}"}]

    if raw_funding and isinstance(raw_funding, list) and "error" not in raw_funding[0]:
        bucketed_values: Dict[str, List[float]] = {}
        for item in raw_funding:
            if not isinstance(item, dict):
                continue
            try:
                timestamp = format_series_timestamp(
                    datetime.utcfromtimestamp(int(item["time"]) / 1000),
                    timeframe,
                )
                funding_rate = float(item["fundingRate"])
            except (KeyError, TypeError, ValueError):
                continue
            bucketed_values.setdefault(timestamp, []).append(funding_rate)

        for period in sorted(bucketed_values):
            observations = bucketed_values[period]
            avg_rate = sum(observations) / len(observations)
            funding_lines.append(
                f"{period}: avg_funding_rate={avg_rate:.8f}, observations={len(observations)}"
            )

    lines = [
        f"# Derivatives metrics for {coin}",
        f"# Reference time: {resolve_analysis_time(curr_date, timeframe=timeframe)}",
        f"# Timeframe: {timeframe}",
        "",
    ]
    lines.append("## Funding Rates")
    if funding_lines:
        lines.extend(funding_lines)
    elif raw_funding and isinstance(raw_funding, list) and "error" in raw_funding[0]:
        lines.append(str(raw_funding[0]["error"]))
    else:
        lines.append("Funding data unavailable.")

    lines.append("")
    lines.append("## Open Interest")
    lines.append(
        "Historical open-interest series is not exposed by the public Hyperliquid info API used here. "
        "Current snapshot is intentionally omitted to avoid look-ahead bias."
    )

    return "\n".join(lines)
