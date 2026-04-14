from __future__ import annotations

import os
from typing import Iterable

import urllib3


KNOWN_QUOTE_ASSETS = ("USDT", "USDC", "BUSD", "FDUSD", "BTC", "ETH", "USD")


def sanitize_symbol(symbol: str) -> str:
    """Normalize free-form crypto symbol input."""
    return (
        symbol.strip()
        .upper()
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )


def extract_base_asset(symbol: str, known_quotes: Iterable[str] = KNOWN_QUOTE_ASSETS) -> str:
    """Extract the base asset from a trading pair or raw symbol."""
    cleaned = sanitize_symbol(symbol)
    for quote in sorted(known_quotes, key=len, reverse=True):
        if cleaned.endswith(quote) and len(cleaned) > len(quote):
            return cleaned[: -len(quote)]
    return cleaned


def normalize_pair(symbol: str, quote_asset: str = "USDT") -> str:
    """Convert free-form symbol input to a Binance-style pair."""
    cleaned = sanitize_symbol(symbol)
    for quote in sorted(KNOWN_QUOTE_ASSETS, key=len, reverse=True):
        if cleaned.endswith(quote) and len(cleaned) > len(quote):
            return cleaned
    return f"{extract_base_asset(cleaned)}{quote_asset.upper()}"


def requests_verify_ssl() -> bool:
    """Return whether HTTPS certificate verification should remain enabled.

    Disable only when running behind a trusted SSL-intercepting proxy or broken
    local certificate store. The secure default stays enabled.
    """
    raw = os.getenv("TRADINGAGENTS_SSL_VERIFY", "true").strip().lower()
    enabled = raw not in {"0", "false", "no", "off"}
    if not enabled:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return enabled
