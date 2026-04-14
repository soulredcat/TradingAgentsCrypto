from tradingagents.agents.utils.agent_utils import build_instrument_context


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["asset_symbol"])
        history = state["investment_debate_state"].get("history", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        tokenomics_report = state["tokenomics_report"]

        investment_debate_state = state["investment_debate_state"]

        curr_situation = (
            f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{tokenomics_report}"
        )
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for rec in past_memories:
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""You are the Research Manager and debate judge for a crypto trading desk. Your job is to review the bull vs bear debate and make one clear call: Buy, Sell, or Hold.

Do not default to Hold unless the evidence is genuinely balanced or the setup is too low-quality to trade.

Your output must do three things:
1. Summarize the strongest evidence from both sides.
2. State a decisive recommendation: Buy, Sell, or Hold.
3. Produce an execution-ready investment plan for the trader covering entry logic, invalidation, key risks, and the time horizon.

Use past mistakes and lessons to improve the quality of the decision.

Past lessons:
"{past_memory_str}"

{instrument_context}

Analyst reports for context:
Market structure report: {market_research_report}
Sentiment report: {sentiment_report}
Crypto catalyst report: {news_report}
Tokenomics report: {tokenomics_report}

Debate history:
{history}"""
        response = llm.invoke(prompt)

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
