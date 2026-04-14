from langchain_core.tools import tool
from typing import Annotated

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_asset_news(
    asset_symbol: Annotated[str, "crypto asset symbol, e.g. BTC, ETH, SUI"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve crypto asset-specific news and catalyst headlines."""
    return route_to_vendor("get_asset_news", asset_symbol, start_date, end_date)


@tool
def get_market_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of items to return"] = 5,
) -> str:
    """Retrieve broad crypto market news."""
    return route_to_vendor("get_market_news", curr_date, look_back_days, limit)


@tool
def get_trending_tokens(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"] = None,
    limit: Annotated[int, "Maximum number of assets to return"] = 5,
) -> str:
    """Retrieve the currently trending crypto assets."""
    return route_to_vendor("get_trending_tokens", curr_date, limit)

