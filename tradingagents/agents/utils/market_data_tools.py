from langchain_core.tools import tool
from typing import Annotated

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_market_data(
    asset_symbol: Annotated[str, "crypto asset symbol or trading pair, e.g. BTC, ETH, SOL/USDT"],
    start_date: Annotated[str, "Start time in YYYY-MM-DD HH:MM format, or YYYY-MM-DD"],
    end_date: Annotated[str, "End time in YYYY-MM-DD HH:MM format, or YYYY-MM-DD"],
) -> str:
    """Retrieve crypto OHLCV market data for a spot pair."""
    return route_to_vendor("get_market_data", asset_symbol, start_date, end_date)


@tool
def get_derivatives_metrics(
    asset_symbol: Annotated[str, "crypto asset symbol or trading pair, e.g. BTC, ETH, SOL/USDT"],
    curr_date: Annotated[str, "Current trading time in YYYY-MM-DD HH:MM format, or YYYY-MM-DD"],
    look_back_days: Annotated[int, "How many days to look back"] = 7,
) -> str:
    """Retrieve funding and open-interest metrics for crypto perpetual futures."""
    return route_to_vendor("get_derivatives_metrics", asset_symbol, curr_date, look_back_days)
