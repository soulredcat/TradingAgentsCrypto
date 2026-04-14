def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        tokenomics_report = state["tokenomics_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Conservative Risk Analyst, your priority is capital protection. Challenge any crypto trade that carries avoidable downside, reflexive liquidation risk, liquidity fragility, or asymmetric event exposure.

Trader decision:
{trader_decision}

Your job is to counter the aggressive and neutral analysts by focusing on:
- Why volatility or momentum can unwind violently.
- Why catalysts may disappoint, be delayed, or already be priced in.
- Why tokenomics, unlocks, dilution, or weak value capture create structural downside.
- Why protecting capital is more important than chasing upside in this setup.

Use these sources:
Market structure report: {market_research_report}
Sentiment report: {sentiment_report}
Crypto catalyst report: {news_report}
Tokenomics report: {tokenomics_report}
Conversation history: {history}
Last aggressive argument: {current_aggressive_response}
Last neutral argument: {current_neutral_response}

Debate directly. Expose weak assumptions and argue for tighter risk control, smaller size, or avoiding the trade entirely when warranted. Output conversationally without special formatting."""

        response = llm.invoke(prompt)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
