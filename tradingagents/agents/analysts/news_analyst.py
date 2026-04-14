from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_asset_news,
    get_language_instruction,
    get_market_news,
)


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_time = state["trade_date"]
        instrument_context = build_instrument_context(state["asset_symbol"])

        tools = [
            get_asset_news,
            get_market_news,
        ]

        system_message = (
            "You are `news_analyst`, the crypto catalyst and event analyst for price action. "
            "Your job is not to summarize headlines. Your job is to decide whether there is a real catalyst, whether it is relevant to this asset, and whether it can change the trading thesis right now. "
            "Use `get_asset_news` for asset-specific catalysts such as protocol announcements, exchange listings or delistings, futures launches, partnership headlines, exploit or security incidents, unlocks, and token-specific narratives. "
            "Use `get_market_news` for broader crypto and macro catalysts such as ETF or futures developments, exchange outages, stablecoin policy, regulatory shifts, CPI or FOMC spillover, and market-wide stress events. "
            "Classify each meaningful event by impact and time decay. Explicitly separate actionable catalysts from noise, recycled headlines, or low-credibility rumors. "
            "If the feed does not provide enough evidence for a category, say that clearly instead of guessing. "
            "Your report must answer these questions:\n"
            "- Is there a real catalyst or not?\n"
            "- Is the event relevant to this asset or mostly noise?\n"
            "- Is the bias bullish, bearish, mixed, or irrelevant?\n"
            "- Is the driver immediate, intraday, or multi-day?\n"
            "- Does the event strengthen or invalidate the current price-action thesis?\n"
            "Structure the report with these sections:\n"
            "1. Headline Verdict\n"
            "2. Catalyst Assessment\n"
            "3. Relevance To Asset\n"
            "4. Risk To Current Thesis\n"
            "5. Event Table\n"
            "In the body and final table, include these fields whenever supported by evidence: `news_bias`, `catalyst_strength`, `event_type`, `time_decay`, and `credibility_score`. "
            "Do not auto-label positive headlines as bullish. Futures launches, ETF rumors, or partnerships can be mixed because they may increase both attention and shorting or dilution risk."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current analysis time is {current_time}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_time=current_time)
        prompt = prompt.partial(instrument_context=instrument_context)

        prompt_value = prompt.invoke({"messages": state["messages"]})
        result = llm.bind_tools(tools).invoke(prompt_value.to_messages())

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
