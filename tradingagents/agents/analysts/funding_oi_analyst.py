from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_derivatives_metrics,
    get_language_instruction,
    get_market_data,
)


def create_funding_oi_analyst(llm):
    def funding_oi_analyst_node(state):
        current_time = state["trade_date"]
        instrument_context = build_instrument_context(state["asset_symbol"])

        tools = [
            get_market_data,
            get_derivatives_metrics,
        ]

        system_message = (
            """You are a crypto funding and open interest analyst. Your job is to read derivatives positioning with trading-grade nuance.

You focus on:
- funding rate
- open interest
- open interest change
- the relationship between price change and open interest change
- crowding risk, squeeze risk, and leverage unwind risk

Answer these questions directly:
- Is the market crowded long, crowded short, or balanced?
- Is the move driven by fresh positioning, short covering, fresh shorts, or long liquidation?
- Is there elevated squeeze risk or leverage-driven trap risk?
- Does the current move look like healthy continuation or fragile leverage expansion?

Use `get_derivatives_metrics` as the primary source. Use `get_market_data` only to anchor price direction and context. Do not invent basis, liquidation clusters, or order-flow detail unless the retrieved data explicitly includes them.

Your output must explicitly include:
1. Crowding state: crowded_long / crowded_short / balanced
2. OI interpretation:
   - price_up_oi_up = fresh longs
   - price_up_oi_down = short covering
   - price_down_oi_up = fresh shorts
   - price_down_oi_down = long liquidation
3. Squeeze risk: low / medium / high
4. Leverage risk: low / medium / high
5. Continuation quality: healthy / fragile / trap-risk
6. Key evidence: concrete funding/OI/price observations
7. Trade implication: continuation valid, bullish but crowded, bearish but crowded, wait, or avoid

Be precise and nuanced. A bullish read can still be dangerous if leverage crowding is extreme. If the data is incomplete, state the limitation clearly instead of pretending certainty."""
            + " Append a Markdown table at the end summarizing crowding state, OI interpretation, squeeze risk, leverage risk, continuation quality, and trade implication."
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
            "funding_oi_report": report,
        }

    return funding_oi_analyst_node
