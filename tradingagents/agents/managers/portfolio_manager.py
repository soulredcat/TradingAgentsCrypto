from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction


def create_portfolio_manager(llm, memory):
    def portfolio_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["asset_symbol"])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        tokenomics_report = state["tokenomics_report"]
        sentiment_report = state["sentiment_report"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        curr_situation = (
            f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{tokenomics_report}"
        )
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for rec in past_memories:
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final crypto trading decision.

{instrument_context}

Rating scale (use exactly one):
- Buy: Strong conviction to enter or add to position.
- Overweight: Favorable outlook, increase exposure gradually.
- Hold: Maintain exposure or stay flat while waiting for confirmation.
- Underweight: Reduce exposure, trim risk, or avoid adding.
- Sell: Exit, avoid entry, or actively de-risk.

Context:
- Research Manager plan: {research_plan}
- Trader proposal: {trader_plan}
- Market structure report: {market_research_report}
- Sentiment report: {sentiment_report}
- Crypto catalyst report: {news_report}
- Tokenomics report: {tokenomics_report}
- Lessons from past decisions: {past_memory_str}

Required output structure:
1. Rating: one of Buy / Overweight / Hold / Underweight / Sell.
2. Executive Summary: action plan covering entry or exit approach, position sizing, invalidation levels, time horizon, and leverage or liquidity constraints.
3. Investment Thesis: the detailed reasoning anchored in the analysts' debate and past lessons.

Risk analysts debate history:
{history}

Be decisive. Ground every conclusion in evidence, and explicitly account for crypto-specific volatility, event risk, and liquidity conditions.{get_language_instruction()}"""

        response = llm.invoke(prompt)

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
        }

    return portfolio_manager_node
