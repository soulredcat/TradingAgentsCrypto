from tradingagents.agents.utils.agent_utils import build_instrument_context


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["asset_symbol"])
        history = state["investment_debate_state"].get("history", "")
        market_research_report = state["market_report"]
        volume_flow_report = state["sentiment_report"]
        funding_oi_report = state["funding_oi_report"]
        news_report = state["news_report"]
        tokenomics_report = state["tokenomics_report"]

        investment_debate_state = state["investment_debate_state"]

        curr_situation = (
            f"{market_research_report}\n\n{volume_flow_report}\n\n{funding_oi_report}\n\n"
            f"{news_report}\n\n{tokenomics_report}"
        )
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for rec in past_memories:
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""You are the Research Manager for a crypto trading desk.

You are not a passive summarizer. Your job is to judge the quality of the bull case and bear case, resolve conflicts, and produce a structured research verdict for the decision layer.

You must answer:
- What is the strongest base case right now?
- What is the strongest alternative case?
- Is there enough edge to pass this to the trader as a real setup, or is this mostly noise / no-trade?
- Which conditions matter most?
- Which conflicts remain unresolved?

Important constraints:
- Do not turn this into a portfolio action like Buy / Sell / Hold as the main output. That belongs to the trader and portfolio layers.
- If the setup quality is weak, say so clearly.
- A valid answer may conclude wait, reduced-size trade, or no-trade.
- Use past mistakes and lessons when they improve judgement quality.

Required output structure:
1. Base Case
2. Alternative Case
3. Net Bias
4. Confidence
5. Tradeability
6. Key Conditions
7. Unresolved Conflicts
8. Recommendation To Decision Layer

Past lessons:
"{past_memory_str}"

{instrument_context}

Analyst reports for context:
Market structure report: {market_research_report}
Volume flow report: {volume_flow_report}
Funding and open interest report: {funding_oi_report}
Crypto catalyst report: {news_report}
Tokenomics and on-chain report: {tokenomics_report}

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
