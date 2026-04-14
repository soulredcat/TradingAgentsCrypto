def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

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

        prompt = f"""You are the Bull Researcher arguing for a long or accumulation stance on the crypto asset. Build the strongest evidence-based bullish case you can and directly rebut the bear case.

Focus on:
- Trend continuation: explain why current price structure, volatility, and participation support upside.
- Structural support: use tokenomics, supply dynamics, adoption, or ecosystem traction to support the thesis.
- Catalysts: highlight protocol upgrades, listings, ecosystem launches, regulatory relief, ETF tailwinds, or other market-moving events.
- Positioning edge: explain why derivatives, funding, or open interest either confirm upside or do not meaningfully invalidate it.
- Risk rebuttal: answer the bear argument point by point and explain which risks are overstated, delayed, or already priced in.

Resources available:
Market structure report: {market_research_report}
Sentiment report: {sentiment_report}
Crypto catalyst report: {news_report}
Tokenomics report: {tokenomics_report}
Debate history: {history}
Last bear argument: {current_response}
Relevant lessons from similar situations: {past_memory_str}

Deliver a sharp debate-style argument. Be specific about why upside asymmetry is attractive despite the risks, and use past lessons where they help."""

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
