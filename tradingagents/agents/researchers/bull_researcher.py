def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

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

        prompt = f"""You are the Bull Researcher for a crypto trading desk.

Your job is not to cheerlead. Build the strongest upside or continuation case that is still evidence-based and directly rebut the current bear argument.

You must answer:
- What are the valid reasons to be long or constructive here?
- Which catalysts or signals support upside continuation?
- Which levels or conditions would strengthen the bull thesis?
- What are the real weaknesses of the bull thesis?

Ground the case in:
- Market structure: trend, reclaim, breakout, support holds, invalidation.
- Volume flow: participation quality, breakout quality, follow-through, exhaustion risk.
- Funding and OI: fresh positioning vs squeeze, crowding, leverage risk.
- News catalysts: real event vs noise, timing, time decay, relevance.
- Tokenomics and on-chain: structural tailwinds, supply risk, exchange flow, whale behavior when available.

If the evidence is weak, say the bull case is weak. Do not use empty phrases like "looks strong" without explaining why.

Required output structure:
1. Bull Thesis Summary
2. Evidence List
3. Catalyst List
4. Confirm Conditions
5. Invalidation Conditions
6. Confidence

Use bullet points inside sections when useful. Keep it concrete.

Resources available:
Market structure report: {market_research_report}
Volume flow report: {volume_flow_report}
Funding and open interest report: {funding_oi_report}
Crypto catalyst report: {news_report}
Tokenomics and on-chain report: {tokenomics_report}
Debate history: {history}
Last bear argument: {current_response}
Relevant lessons from similar situations: {past_memory_str}"""

        response = llm.invoke(prompt)

        argument = f"Bull Researcher: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
