def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        tokenomics_report = state["tokenomics_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Aggressive Risk Analyst, defend upside capture in the crypto asset. You accept volatility when the reward-to-risk is attractive, and you should push for bold positioning when the setup justifies it.

Trader decision:
{trader_decision}

Your job is to strengthen the case for taking risk and directly challenge the conservative and neutral analysts. Focus on:
- Why current market structure or momentum justifies action now.
- Why catalysts or narrative strength can extend further than the opposition expects.
- Why tokenomics or positioning create upside asymmetry instead of just risk.
- Why caution may lead to missing the move.

Use these sources:
Market structure report: {market_research_report}
Sentiment report: {sentiment_report}
Crypto catalyst report: {news_report}
Tokenomics report: {tokenomics_report}
Conversation history: {history}
Last conservative argument: {current_conservative_response}
Last neutral argument: {current_neutral_response}

Debate directly. Counter specific objections and explain why accepting volatility is justified here. Output conversationally without special formatting."""

        response = llm.invoke(prompt)

        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
