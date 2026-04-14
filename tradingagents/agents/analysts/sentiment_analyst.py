from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_asset_news,
    get_language_instruction,
    get_trending_tokens,
)


def create_sentiment_analyst(llm):
    def sentiment_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["asset_symbol"])
        look_back_start = (datetime.strptime(current_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")

        tools = [
            get_asset_news,
            get_trending_tokens,
        ]

        system_message = (
            "You are a crypto sentiment analyst. Measure whether the target asset is gaining or losing attention, "
            "whether the narrative is crowded, and whether the sentiment backdrop supports continuation or warns of exhaustion. "
            "Use `get_asset_news` for asset-specific headlines and `get_trending_tokens` for cross-market attention context. "
            "Focus on retail participation, social crowding, narrative strength, and momentum in attention. "
            "Write a detailed report with explicit bullish, bearish, and crowding-risk takeaways."
            + " Make sure to append a Markdown table at the end of the report to organize key points."
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
                    "For your reference, the current date is {current_date}, the lookback starts at {look_back_start}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(look_back_start=look_back_start)
        prompt = prompt.partial(instrument_context=instrument_context)

        prompt_value = prompt.invoke({"messages": state["messages"]})
        result = llm.bind_tools(tools).invoke(prompt_value.to_messages())

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "sentiment_report": report,
        }

    return sentiment_analyst_node

