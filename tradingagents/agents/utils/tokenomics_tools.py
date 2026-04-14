from langchain_core.tools import tool
from typing import Annotated

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_tokenomics(
    asset_symbol: Annotated[str, "crypto asset symbol, e.g. BTC, ETH, SUI"],
    curr_date: Annotated[str, "Current analysis time in YYYY-MM-DD HH:MM format, or YYYY-MM-DD"] = None,
) -> str:
    """Retrieve tokenomics, supply, and valuation metadata for a crypto asset."""
    return route_to_vendor("get_tokenomics", asset_symbol, curr_date)
