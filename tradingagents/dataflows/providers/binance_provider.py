from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

import pandas as pd
import requests
from stockstats import wrap

from tradingagents.dataflows.config import get_config

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


def _fetch_klines(pair: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    rows: List[List[object]] = []
    cursor = start_ms

    while cursor < end_ms:
        batch = _request(
            BINANCE_SPOT_BASE_URL,
            "/api/v3/klines",
            {
                "symbol": pair,
                "interval": "1d",
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1000,
            },
        )
        if not isinstance(batch, list) or not batch:
            break

        rows.extend(batch)
        last_open_time = int(batch[-1][0])
        next_cursor = last_open_time + 86_400_000
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
    config = get_config()
    quote_asset = _quote_asset()
    pair = normalize_pair(asset_symbol, quote_asset=quote_asset)

    curr_date_dt = pd.to_datetime(curr_date).normalize()
    start_dt = curr_date_dt - timedelta(days=history_days)
    end_dt = curr_date_dt + timedelta(days=1)

    data = _fetch_klines(
        pair,
        int(start_dt.timestamp() * 1000),
        int(end_dt.timestamp() * 1000),
    )
    return data[data["Date"] <= curr_date_dt]


def get_market_data(asset_symbol: str, start_date: str, end_date: str) -> str:
    """Return OHLCV market data for a crypto spot pair."""
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
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

    csv_string = data.to_csv(index=False)
    header = f"# Crypto market data for {pair} from {start_date} to {end_date}\n"
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
    wrapped["Date"] = wrapped["Date"].dt.strftime("%Y-%m-%d")
    wrapped[indicator]

    values_by_date = {}
    for _, row in wrapped.iterrows():
        date_key = row["Date"]
        value = row[indicator]
        values_by_date[date_key] = "N/A" if pd.isna(value) else str(value)

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_date_dt - timedelta(days=look_back_days)
    lines: List[str] = []
    cursor = curr_date_dt
    while cursor >= start_dt:
        date_key = cursor.strftime("%Y-%m-%d")
        lines.append(f"{date_key}: {values_by_date.get(date_key, 'N/A')}")
        cursor -= timedelta(days=1)

    pair = normalize_pair(asset_symbol, quote_asset=_quote_asset())
    return (
        f"## {indicator} values for {pair} from {start_dt.strftime('%Y-%m-%d')} to {curr_date}\n\n"
        + "\n".join(lines)
        + "\n\n"
        + _INDICATOR_DESCRIPTIONS[indicator]
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
            {"symbol": pair, "limit": max(look_back_days, 3)},
        )
        if isinstance(raw_funding, list):
            funding = raw_funding[-look_back_days:]
    except requests.RequestException as exc:
        funding = [{"error": f"Funding data unavailable: {exc}"}]

    try:
        raw_oi = _request(
            BINANCE_FUTURES_BASE_URL,
            "/futures/data/openInterestHist",
            {"symbol": pair, "period": "1d", "limit": max(look_back_days, 3)},
        )
        if isinstance(raw_oi, list):
            open_interest = raw_oi[-look_back_days:]
    except requests.RequestException as exc:
        open_interest = [{"error": f"Open interest data unavailable: {exc}"}]

    lines = [f"# Derivatives metrics for {pair}", f"# Reference date: {curr_date}", ""]

    lines.append("## Funding Rates")
    if funding and "error" not in funding[0]:
        for item in funding:
            timestamp = datetime.utcfromtimestamp(int(item["fundingTime"]) / 1000).strftime("%Y-%m-%d")
            lines.append(f"{timestamp}: funding_rate={item['fundingRate']}")
    else:
        lines.append(funding[0]["error"] if funding else "Funding data unavailable.")

    lines.append("")
    lines.append("## Open Interest")
    if open_interest and "error" not in open_interest[0]:
        for item in open_interest:
            timestamp = datetime.utcfromtimestamp(int(item["timestamp"]) / 1000).strftime("%Y-%m-%d")
            lines.append(
                f"{timestamp}: open_interest={item['sumOpenInterest']}, open_interest_value={item['sumOpenInterestValue']}"
            )
    else:
        lines.append(open_interest[0]["error"] if open_interest else "Open interest data unavailable.")

    return "\n".join(lines)
