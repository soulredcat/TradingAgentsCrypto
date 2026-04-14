import functools

from tradingagents.agents.utils.agent_utils import build_instrument_context


def create_trader(llm, memory):
    def trader_node(state, name):
        asset_symbol = state["asset_symbol"]
        instrument_context = build_instrument_context(asset_symbol)
        investment_plan = state["investment_plan"]
        setup_classification = state["setup_classification"]
        decision_plan = state["decision_plan"]
        market_research_report = state["market_report"]
        volume_flow_report = state["sentiment_report"]
        funding_oi_report = state["funding_oi_report"]
        news_report = state["news_report"]
        tokenomics_report = state["tokenomics_report"]

        curr_situation = (
            f"{market_research_report}\n\n{volume_flow_report}\n\n{funding_oi_report}\n\n"
            f"{news_report}\n\n{tokenomics_report}\n\n{setup_classification}\n\n{decision_plan}"
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
                f"Here is the current research verdict for {asset_symbol}. {instrument_context} "
                "Use the analyst work and the research verdict below to decide whether to buy, sell, or hold the crypto asset at the current analysis time. "
                "Be explicit about timing, invalidation, and the main execution risk.\n\n"
                f"Market structure report: {market_research_report}\n\n"
                f"Volume flow report: {volume_flow_report}\n\n"
                f"Funding and open interest report: {funding_oi_report}\n\n"
                f"Crypto catalyst report: {news_report}\n\n"
                f"Tokenomics and on-chain report: {tokenomics_report}\n\n"
                f"Research verdict: {investment_plan}\n\n"
                f"Setup classification: {setup_classification}\n\n"
                f"Decision engine recommendation: {decision_plan}\n\n"
                "Available risk gates before execution:\n"
                f"- Trade Risk Analyst assessment: {state.get('trade_risk_assessment', '')}\n"
                f"- Portfolio Risk Analyst assessment: {state.get('portfolio_risk_assessment', '')}"
            ),
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "You are the Execution Team converting approved analysis into an executable crypto trading plan. "
                    "Respect the setup classification, decision engine, and upstream risk gates instead of forcing a trade when the setup is not ready. "
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

    return functools.partial(trader_node, name="Execution Team")
