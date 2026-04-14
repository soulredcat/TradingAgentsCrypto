import functools

from tradingagents.agents.utils.agent_utils import build_instrument_context


def create_trader(llm, memory):
    def trader_node(state, name):
        asset_symbol = state["asset_symbol"]
        instrument_context = build_instrument_context(asset_symbol)
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        tokenomics_report = state["tokenomics_report"]

        curr_situation = (
            f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{tokenomics_report}"
        )
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for rec in past_memories:
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        context = {
            "role": "user",
            "content": (
                f"Here is the current investment plan for {asset_symbol}. {instrument_context} "
                "Use the analyst work and the plan below to decide whether to buy, sell, or hold the crypto asset today. "
                "Be explicit about timing, invalidation, and the main execution risk.\n\n"
                f"Market structure report: {market_research_report}\n\n"
                f"Sentiment report: {sentiment_report}\n\n"
                f"Crypto catalyst report: {news_report}\n\n"
                f"Tokenomics report: {tokenomics_report}\n\n"
                f"Proposed investment plan: {investment_plan}"
            ),
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "You are the trader converting research into an executable crypto trading decision. "
                    "Provide a specific recommendation to buy, sell, or hold. "
                    "Explain the setup, timing, invalidation, and main execution risk. "
                    "Always end with 'FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**'. "
                    f"Apply lessons from past decisions where relevant: {past_memory_str}"
                ),
            },
            context,
        ]

        result = llm.invoke(messages)

        return {
            "messages": [result],
            "trader_investment_plan": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
