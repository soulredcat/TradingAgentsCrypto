def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        volume_flow_report = state["sentiment_report"]
        funding_oi_report = state["funding_oi_report"]
        news_report = state["news_report"]
        tokenomics_report = state["tokenomics_report"]

        curr_situation = (
            f"{market_research_report}\n\n{volume_flow_report}\n\n{funding_oi_report}\n\n"
            f"{news_report}\n\n{tokenomics_report}"
        )
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for rec in past_memories:
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""You are the Bear Researcher for a crypto trading desk.

Your job is not to be negative for its own sake. Build the strongest downside, failure, or no-trade case you can and directly challenge the current bull argument.

You must answer:
- What are the valid reasons to short, avoid, reduce, or refuse this setup?
- Why could the current move fail, trap, or reverse?
- Which risks are not fully reflected in price yet?
- Which levels or conditions would invalidate the bull thesis?

Ground the case in:
- Market structure: failed reclaim, contested higher timeframe, lower highs, breakdown risk.
- Volume flow: weak participation, fake breakout risk, exhaustion, absorption, lack of follow-through.
- Funding and OI: crowded longs, leverage-driven move, short covering only, squeeze reversal risk.
- News catalysts: negative event risk, rumor quality, short-lived headline pop, adverse macro or security event.
- Tokenomics and on-chain: unlock overhang, dilution, exchange inflow, whale distribution, structural headwind.

If the evidence is weak, say the bear case is weak. Do not hide behind vague phrases like "momentum may fade" without explaining why.

Required output structure:
1. Bear Thesis Summary
2. Evidence List
3. Failure Conditions
4. Downside Triggers
5. Trap Risk
6. Confidence

Use bullet points inside sections when useful. Keep it concrete.

Resources available:
Market structure report: {market_research_report}
Volume flow report: {volume_flow_report}
Funding and open interest report: {funding_oi_report}
Crypto catalyst report: {news_report}
Tokenomics and on-chain report: {tokenomics_report}
Debate history: {history}
Last bull argument: {current_response}
Relevant lessons from similar situations: {past_memory_str}"""

        response = llm.invoke(prompt)

        argument = f"Bear Researcher: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
