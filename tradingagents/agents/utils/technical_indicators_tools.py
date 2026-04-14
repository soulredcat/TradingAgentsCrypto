from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_indicators(
    asset_symbol: Annotated[str, "crypto asset symbol or trading pair, e.g. BTC, ETH, SOL/USDT"],
    indicator: Annotated[str, "technical indicator to retrieve"],
    curr_date: Annotated[str, "The current trading date in YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 30,
) -> str:
    """
    Retrieve a single technical indicator for a crypto asset or pair.
    Uses the configured technical_indicators vendor.
    Args:
        asset_symbol (str): Asset symbol or trading pair, e.g. BTC, ETH, SOL/USDT
        indicator (str): A single technical indicator name, e.g. 'rsi', 'macd'. Call this tool once per indicator.
        curr_date (str): The current trading date in YYYY-mm-dd
        look_back_days (int): How many days to look back, default is 30
    Returns:
        str: A formatted report containing the requested technical indicator series.
    """
    # LLMs sometimes pass multiple indicators as a comma-separated string;
    # split and process each individually.
    indicators = [i.strip().lower() for i in indicator.split(",") if i.strip()]
    results = []
    for ind in indicators:
        try:
            results.append(route_to_vendor("get_indicators", asset_symbol, ind, curr_date, look_back_days))
        except ValueError as e:
            results.append(str(e))
    return "\n\n".join(results)
