from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Tuple

import requests

from .crypto_common import extract_base_asset, requests_verify_ssl


COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
COMMON_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "SUI": "sui",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "TON": "the-open-network",
}


def _request(path: str, params: Dict[str, object]) -> Dict[str, object] | List[object]:
    response = requests.get(
        f"{COINGECKO_BASE_URL}{path}",
        params=params,
        timeout=20,
        headers={"Accept": "application/json"},
        verify=requests_verify_ssl(),
    )
    response.raise_for_status()
    return response.json()


def _resolve_coin(asset_symbol: str) -> Tuple[str, Dict[str, object]]:
    base_asset = extract_base_asset(asset_symbol)
    coin_id = COMMON_IDS.get(base_asset)
    if coin_id:
        return coin_id, {"symbol": base_asset}

    payload = _request("/search", {"query": base_asset})
    coins = payload.get("coins", []) if isinstance(payload, dict) else []
    for coin in coins:
        if str(coin.get("symbol", "")).upper() == base_asset:
            return str(coin["id"]), coin
    if coins:
        return str(coins[0]["id"]), coins[0]
    raise ValueError(f"Unable to resolve crypto asset '{asset_symbol}' on CoinGecko.")


def get_tokenomics(asset_symbol: str, curr_date: str | None = None) -> str:
    """Return tokenomics and market structure metadata for a crypto asset."""
    try:
        coin_id, coin_ref = _resolve_coin(asset_symbol)
        payload = _request(
            f"/coins/{coin_id}",
            {
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "true",
                "developer_data": "false",
                "sparkline": "false",
            },
        )
    except (ValueError, requests.RequestException) as exc:
        return f"CoinGecko tokenomics unavailable for {asset_symbol}: {exc}"

    market_data = payload.get("market_data", {}) if isinstance(payload, dict) else {}
    community_data = payload.get("community_data", {}) if isinstance(payload, dict) else {}

    fields = [
        ("Name", payload.get("name")),
        ("Symbol", str(payload.get("symbol", coin_ref.get("symbol", ""))).upper()),
        ("CoinGecko ID", coin_id),
        ("Asset Platform", payload.get("asset_platform_id")),
        ("Categories", ", ".join(payload.get("categories", [])[:6]) if payload.get("categories") else None),
        ("Genesis Date", payload.get("genesis_date")),
        ("Market Cap Rank", payload.get("market_cap_rank")),
        ("Current Price (USD)", market_data.get("current_price", {}).get("usd")),
        ("Market Cap (USD)", market_data.get("market_cap", {}).get("usd")),
        ("Fully Diluted Valuation (USD)", market_data.get("fully_diluted_valuation", {}).get("usd")),
        ("24h Volume (USD)", market_data.get("total_volume", {}).get("usd")),
        ("Circulating Supply", market_data.get("circulating_supply")),
        ("Total Supply", market_data.get("total_supply")),
        ("Max Supply", market_data.get("max_supply")),
        ("ATH (USD)", market_data.get("ath", {}).get("usd")),
        ("ATH Change %", market_data.get("ath_change_percentage", {}).get("usd")),
        ("ATL (USD)", market_data.get("atl", {}).get("usd")),
        ("Twitter Followers", community_data.get("twitter_followers")),
        ("Telegram Users", community_data.get("telegram_channel_user_count")),
    ]

    lines = [
        f"# Tokenomics and market profile for {payload.get('name', asset_symbol)}",
        f"# Retrieved at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "",
    ]
    for label, value in fields:
        if value is not None:
            lines.append(f"{label}: {value}")

    description = str(payload.get("description", {}).get("en", "")).strip()
    if description:
        compact = " ".join(description.split())
        lines.extend(["", "Description:", compact[:900]])

    return "\n".join(lines)


def get_trending_tokens(curr_date: str | None = None, limit: int = 5) -> str:
    """Return currently trending crypto assets from CoinGecko."""
    try:
        payload = _request("/search/trending", {})
    except requests.RequestException as exc:
        return f"CoinGecko trending data unavailable: {exc}"
    coins = payload.get("coins", []) if isinstance(payload, dict) else []

    lines = [
        "# Trending crypto assets",
        f"# Retrieved at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "",
    ]
    for index, item in enumerate(coins[:limit], start=1):
        coin = item.get("item", {})
        lines.append(
            f"{index}. {coin.get('name')} ({str(coin.get('symbol', '')).upper()}) - "
            f"market_cap_rank={coin.get('market_cap_rank')}, score={coin.get('score')}"
        )

    return "\n".join(lines)
