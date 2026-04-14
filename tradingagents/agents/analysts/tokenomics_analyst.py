from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_tokenomics,
)


def create_tokenomics_analyst(llm):
    def tokenomics_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["asset_symbol"])

        tools = [
            get_tokenomics,
        ]

        system_message = (
            "You are a crypto tokenomics analyst. Evaluate dilution risk, float quality, market cap versus fully diluted valuation, "
            "supply overhang, and whether the asset structure supports upside or creates asymmetric downside. "
            "Use `get_tokenomics` to pull supply, valuation, rank, and community metrics. "
            "Your report must clearly separate structural strengths from structural dilution or valuation risk."
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
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
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

