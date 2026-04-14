from .providers.binance_provider import (
    get_derivatives_metrics as get_binance_derivatives_metrics,
    get_indicator_window as get_binance_indicator_window,
    get_market_data as get_binance_market_data,
)
from .providers.coingecko_provider import (
    get_tokenomics as get_coingecko_tokenomics,
    get_trending_tokens as get_coingecko_trending_tokens,
)
from .providers.crypto_news_provider import (
    get_asset_news as get_google_asset_news,
    get_market_news as get_google_market_news,
)
from .providers.hyperliquid_provider import (
    get_derivatives_metrics as get_hyperliquid_derivatives_metrics,
    get_indicator_window as get_hyperliquid_indicator_window,
    get_market_data as get_hyperliquid_market_data,
)

# Configuration and routing logic
from .config import get_config

# Tools organized by category
TOOLS_CATEGORIES = {
    "market_data": {
        "description": "Crypto OHLCV spot market data",
        "tools": [
            "get_market_data"
        ]
    },
    "technical_indicators": {
        "description": "Crypto market structure indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "tokenomics_data": {
        "description": "Tokenomics, supply, and valuation metadata",
        "tools": [
            "get_tokenomics"
        ]
    },
    "derivatives_data": {
        "description": "Funding and open-interest metrics",
        "tools": [
            "get_derivatives_metrics"
        ]
    },
    "news_data": {
        "description": "Crypto asset and market news",
        "tools": [
            "get_asset_news",
            "get_market_news",
            "get_trending_tokens",
        ]
    }
}

VENDOR_LIST = [
    "binance",
    "coingecko",
    "google_news",
    "hyperliquid",
]

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    "get_market_data": {
        "hyperliquid": get_hyperliquid_market_data,
        "binance": get_binance_market_data,
    },
    "get_indicators": {
        "hyperliquid": get_hyperliquid_indicator_window,
        "binance": get_binance_indicator_window,
    },
    "get_tokenomics": {
        "coingecko": get_coingecko_tokenomics,
    },
    "get_derivatives_metrics": {
        "hyperliquid": get_hyperliquid_derivatives_metrics,
        "binance": get_binance_derivatives_metrics,
    },
    "get_asset_news": {
        "google_news": get_google_asset_news,
    },
    "get_market_news": {
        "google_news": get_google_market_news,
    },
    "get_trending_tokens": {
        "coingecko": get_coingecko_trending_tokens,
    },
}


def _is_vendor_unavailable_response(result) -> bool:
    return isinstance(result, str) and " unavailable" in result.lower()

def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")

def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    # Build fallback chain: primary vendors first, then remaining available vendors
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    last_error = None
    last_vendor = None
    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            result = impl_func(*args, **kwargs)
            if _is_vendor_unavailable_response(result):
                last_error = RuntimeError(result)
                last_vendor = vendor
                continue
            return result
        except Exception as exc:
            last_error = exc
            last_vendor = vendor
            continue

    if last_error is not None:
        raise RuntimeError(
            f"No available vendor for '{method}'. Last vendor '{last_vendor}' failed: {last_error}"
        ) from last_error
    raise RuntimeError(f"No available vendor for '{method}'")
