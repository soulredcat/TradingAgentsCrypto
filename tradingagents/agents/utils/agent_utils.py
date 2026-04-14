from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.market_data_tools import (
    get_derivatives_metrics,
    get_market_data,
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.tokenomics_tools import (
    get_tokenomics,
)
from tradingagents.agents.utils.crypto_news_tools import (
    get_asset_news,
    get_market_news,
    get_trending_tokens,
)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Only applied to user-facing agents (analysts, portfolio manager).
    Internal debate agents stay in English for reasoning quality.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def build_instrument_context(asset_symbol: str) -> str:
    """Describe the exact instrument so agents preserve the provided symbol."""
    return (
        f"The instrument to analyze is `{asset_symbol}`. "
        "Use this exact symbol or pair in every tool call, report, and recommendation. "
        "Preserve quote assets and exchange suffixes when provided "
        "(e.g. `BTC-PERP`, `ETH/USDT`, `SUIUSDT`, `7203.T`)."
    )

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
