from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

import pandas as pd
import requests
from stockstats import wrap

from tradingagents.dataflows.config import get_config
from tradingagents.time_utils import (
    format_series_timestamp,
    parse_analysis_time,
    resolve_analysis_time,
    timeframe_to_timedelta,
)

from .crypto_common import extract_base_asset, normalize_pair, requests_verify_ssl


BINANCE_SPOT_BASE_URL = "https://api.binance.com"
BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"

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


def _request(base_url: str, path: str, params: Dict[str, object]) -> List[object] | Dict[str, object]:
    response = requests.get(
        f"{base_url}{path}",
        params=params,
        timeout=20,
        headers={"Accept": "application/json"},
        verify=requests_verify_ssl(),
    )
    response.raise_for_status()
    return response.json()


def _quote_asset() -> str:
    return str(get_config().get("quote_asset", "USDT")).upper()


def _timeframe() -> str:
    return str(get_config().get("timeframe", "1h")).lower()


def _timeframe_delta() -> timedelta:
    return timeframe_to_timedelta(_timeframe())


def _periods_per_day() -> int:
    return max(int(timedelta(days=1) / _timeframe_delta()), 1)


def _fetch_klines(pair: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    rows: List[List[object]] = []
    cursor = start_ms
    interval = _timeframe()
    interval_ms = int(_timeframe_delta().total_seconds() * 1000)

    while cursor < end_ms:
        batch = _request(
            BINANCE_SPOT_BASE_URL,
            "/api/v3/klines",
            {
                "symbol": pair,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1000,
            },
        )
        if not isinstance(batch, list) or not batch:
            break

        rows.extend(batch)
        last_open_time = int(batch[-1][0])
        next_cursor = last_open_time + interval_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor

    columns = [
        "open_time",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "close_time",
        "quote_volume",
        "trade_count",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "ignore",
    ]
    data = pd.DataFrame(rows, columns=columns)
    if data.empty:
        return data

    data["Date"] = pd.to_datetime(data["open_time"], unit="ms")
    for column in ("Open", "High", "Low", "Close", "Volume"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data[["Date", "Open", "High", "Low", "Close", "Volume"]].dropna()


def load_ohlcv(asset_symbol: str, curr_date: str, history_days: int = 420) -> pd.DataFrame:
    """Load cached OHLCV for a crypto pair without look-ahead bias."""
    quote_asset = _quote_asset()
    pair = normalize_pair(asset_symbol, quote_asset=quote_asset)
    timeframe = _timeframe()

    curr_date_dt = pd.Timestamp(parse_analysis_time(curr_date, timeframe=timeframe))
    start_dt = curr_date_dt - timedelta(days=history_days)
    end_dt = curr_date_dt + _timeframe_delta()

    data = _fetch_klines(
        pair,
        int(start_dt.timestamp() * 1000),
        int(end_dt.timestamp() * 1000),
    )
    return data[data["Date"] <= curr_date_dt]


def get_market_data(asset_symbol: str, start_date: str, end_date: str) -> str:
    """Return OHLCV market data for a crypto spot pair."""
    timeframe = _timeframe()
    try:
        start_dt = parse_analysis_time(start_date, timeframe=timeframe)
        end_dt = parse_analysis_time(end_date, timeframe=timeframe) + _timeframe_delta()
        pair = normalize_pair(asset_symbol, quote_asset=_quote_asset())
        data = _fetch_klines(
            pair,
            int(start_dt.timestamp() * 1000),
            int(end_dt.timestamp() * 1000),
        )
    except (ValueError, requests.RequestException) as exc:
        return f"Binance market data unavailable for {asset_symbol}: {exc}"

    if data.empty:
        return f"No crypto market data found for pair '{pair}' between {start_date} and {end_date}."

    formatted = data.copy()
    formatted["Date"] = formatted["Date"].apply(lambda value: format_series_timestamp(value, timeframe))
    csv_string = formatted.to_csv(index=False)
    header = (
        f"# Crypto market data for {pair} from {resolve_analysis_time(start_date, timeframe=timeframe)} "
        f"to {resolve_analysis_time(end_date, timeframe=timeframe)}\n"
    )
    header += f"# Timeframe: {timeframe}\n"
    header += f"# Records: {len(data)}\n"
    header += f"# Retrieved at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
    return header + csv_string


def get_indicator_window(asset_symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
    """Calculate indicator values over a crypto lookback window."""
    indicator = indicator.strip().lower()
    if indicator not in _INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"Indicator '{indicator}' is not supported. Choose from: {sorted(_INDICATOR_DESCRIPTIONS)}"
        )

    try:
        data = load_ohlcv(asset_symbol, curr_date, history_days=max(420, look_back_days + 220))
    except (ValueError, requests.RequestException) as exc:
        return f"Binance indicator data unavailable for {asset_symbol}: {exc}"
    if data.empty:
        return f"No OHLCV data available for '{asset_symbol}' to compute {indicator}."

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

    pair = normalize_pair(asset_symbol, quote_asset=_quote_asset())
    truncation_note = ""
    if cursor >= start_dt:
        truncation_note = f"\n\nWindow truncated to the latest {max_points} {timeframe} periods for readability."
    return (
        f"## {indicator} values for {pair} from {format_series_timestamp(start_dt, timeframe)} "
        f"to {resolve_analysis_time(curr_date, timeframe=timeframe)}\n\n"
        + "\n".join(lines)
        + "\n\n"
        + _INDICATOR_DESCRIPTIONS[indicator]
        + truncation_note
    )


def get_derivatives_metrics(asset_symbol: str, curr_date: str, look_back_days: int = 7) -> str:
    """Fetch Binance futures funding and open-interest history."""
    pair = normalize_pair(asset_symbol, quote_asset=_quote_asset())
    funding = []
    open_interest = []

    try:
        raw_funding = _request(
            BINANCE_FUTURES_BASE_URL,
            "/fapi/v1/fundingRate",
            {"symbol": pair, "limit": max(look_back_days * 3, 3)},
        )
        if isinstance(raw_funding, list):
            funding = raw_funding[-max(look_back_days * 3, 3):]
    except requests.RequestException as exc:
        funding = [{"error": f"Funding data unavailable: {exc}"}]

    try:
        raw_oi = _request(
            BINANCE_FUTURES_BASE_URL,
            "/futures/data/openInterestHist",
            {
                "symbol": pair,
                "period": _timeframe(),
                "limit": max(look_back_days * _periods_per_day(), 3),
            },
        )
        if isinstance(raw_oi, list):
            open_interest = raw_oi[-max(look_back_days * _periods_per_day(), 3):]
    except requests.RequestException as exc:
        open_interest = [{"error": f"Open interest data unavailable: {exc}"}]

    timeframe = _timeframe()
    lines = [
        f"# Derivatives metrics for {pair}",
        f"# Reference time: {resolve_analysis_time(curr_date, timeframe=timeframe)}",
        f"# Timeframe: {timeframe}",
        "",
    ]

    lines.append("## Funding Rates")
    if funding and "error" not in funding[0]:
        for item in funding:
            timestamp = format_series_timestamp(
                datetime.utcfromtimestamp(int(item["fundingTime"]) / 1000),
                timeframe,
            )
            lines.append(f"{timestamp}: funding_rate={item['fundingRate']}")
    else:
        lines.append(funding[0]["error"] if funding else "Funding data unavailable.")

    lines.append("")
    lines.append("## Open Interest")
    if open_interest and "error" not in open_interest[0]:
        for item in open_interest:
            timestamp = format_series_timestamp(
                datetime.utcfromtimestamp(int(item["timestamp"]) / 1000),
                timeframe,
            )
            lines.append(
                f"{timestamp}: open_interest={item['sumOpenInterest']}, open_interest_value={item['sumOpenInterestValue']}"
            )
    else:
        lines.append(open_interest[0]["error"] if open_interest else "Open interest data unavailable.")

    return "\n".join(lines)
