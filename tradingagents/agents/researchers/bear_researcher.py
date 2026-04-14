def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        tokenomics_report = state["tokenomics_report"]

        curr_situation = (
            f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{tokenomics_report}"
        )
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for rec in past_memories:
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""You are the Bear Researcher arguing against taking a long position in the crypto asset. Build the strongest evidence-based bearish case you can and directly rebut the bull case.

Focus on:
- Downside path: explain where price structure, momentum, volatility, or market participation imply exhaustion or breakdown risk.
- Structural weakness: use tokenomics, dilution risk, unlock overhang, weak utility, or poor value capture to challenge the asset.
- Catalyst risk: highlight exchange risk, regulatory shocks, ecosystem failures, exploit risk, macro tightening, or narrative decay.
- Positioning risk: explain how derivatives, funding, or open interest may signal crowded longs, reflexive downside, or liquidation risk.
- Bull rebuttal: challenge optimistic assumptions directly and show what is underappreciated or not yet priced.

Resources available:
Market structure report: {market_research_report}
Sentiment report: {sentiment_report}
Crypto catalyst report: {news_report}
Tokenomics report: {tokenomics_report}
Debate history: {history}
Last bull argument: {current_response}
Relevant lessons from similar situations: {past_memory_str}

Deliver a sharp debate-style argument. Be specific about why the downside or no-trade case is stronger than the upside case, and use past lessons where they help."""

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
