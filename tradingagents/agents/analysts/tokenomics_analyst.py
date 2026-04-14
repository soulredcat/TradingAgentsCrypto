from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_tokenomics,
)


def create_tokenomics_analyst(llm):
    def tokenomics_analyst_node(state):
        current_time = state["trade_date"]
        instrument_context = build_instrument_context(state["asset_symbol"])

        tools = [
            get_tokenomics,
        ]

        system_message = (
            """You are `tokenomics_onchain_analyst`, the crypto analyst responsible for structural supply risk and any on-chain evidence that is actually available.

Your job is to evaluate whether the asset has durable tailwinds or hidden structural risk from dilution, unlocks, concentration, exchange flow pressure, whale behavior, or weakening network participation.

Answer these questions directly:
- Is supply risk low, medium, or high?
- Is there an unlock or vesting risk window that matters to the trade?
- Do available signals suggest exchange inflow, exchange outflow, or neutral flow bias?
- Is whale or concentration behavior supportive, risky, or unavailable?
- Is on-chain participation improving, weakening, or unavailable from the current evidence?
- Does the asset have a structural tailwind or headwind for this trade?

Use `get_tokenomics` to pull the available supply, valuation, rank, category, and community metrics first. This repo does not guarantee real unlock calendars, exchange wallet flow, whale transfer feeds, TVL, staking, or bridge metrics. If those inputs are not present in the retrieved data, say they are unavailable. Do not invent on-chain evidence.

Your report must explicitly include:
1. Supply risk: low / medium / high
2. Unlock risk window
3. Exchange flow bias: inflow / outflow / neutral / unavailable
4. Whale activity bias: bullish / bearish / mixed / unavailable
5. On-chain participation state: improving / weakening / stable / unavailable
6. Structural tailwind or structural headwind
7. Trade implication: overweight, normal size, smaller size, or avoid overweight

Ground the analysis in what the data actually supports. A good chart does not cancel bad token structure, concentration risk, or dilution overhang. Append a Markdown table at the end summarizing the structural read."""
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
            "tokenomics_report": report,
        }

    return tokenomics_analyst_node


def create_tokenomics_onchain_analyst(llm):
    return create_tokenomics_analyst(llm)
