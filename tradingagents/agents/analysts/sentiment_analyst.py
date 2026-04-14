from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_derivatives_metrics,
    get_indicators,
    get_language_instruction,
    get_market_data,
)


def create_volume_flow_analyst(llm):
    def volume_flow_analyst_node(state):
        current_time = state["trade_date"]
        instrument_context = build_instrument_context(state["asset_symbol"])

        tools = [
            get_market_data,
            get_indicators,
            get_derivatives_metrics,
        ]

        system_message = (
            """You are a crypto volume flow analyst. Your job is to judge whether the latest move is supported by real participation or is weak, noisy, and vulnerable to failure.

Your report must answer these questions directly:
- Is the breakout or directional move confirmed by volume and participation, or is it weak?
- Is the current move expanding with healthy follow-through, fading, or mixed?
- Are there signs of exhaustion, absorption, rejection, or one-sided dominance?
- Does derivatives positioning confirm buyer/seller dominance or warn of crowding risk?

Use `get_market_data` first to inspect OHLCV and raw volume behavior, then use `get_indicators` to pull the most relevant confirmation indicators, and finally use `get_derivatives_metrics` to judge whether funding and open interest align with the move. You do not have order book, tape, or true aggressor delta unless it is explicitly available in the retrieved data, so do not invent them.

Choose up to **6 indicators** that help validate participation and flow quality without redundancy. Prioritize indicators that help judge trend participation, exhaustion, and breakout quality, such as:
- vwma
- close_10_ema
- close_20_sma
- rsi
- macd / macdh
- atr

Your output must explicitly include:
1. Breakout quality: confirmed / weak / fake-risk
2. Participation state: expanding / fading / mixed
3. Flow bias: buyer_dominant / seller_dominant / mixed
4. Exhaustion flag: true / false
5. Key evidence: concrete volume or positioning observations
6. Trade implication: follow, wait for confirmation, or fade-risk
7. Invalidation context: what price/flow behavior would disprove the read

Make the report concrete and trading-oriented. If the available data is insufficient for a strong call, say so clearly instead of pretending certainty."""
            + " Append a Markdown table at the end summarizing breakout quality, participation state, flow bias, exhaustion flag, and trade implication."
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
            "sentiment_report": report,
        }

    return volume_flow_analyst_node


def create_sentiment_analyst(llm):
    return create_volume_flow_analyst(llm)
