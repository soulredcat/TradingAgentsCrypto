def create_trade_risk_analyst(llm):
    def trade_risk_node(state) -> dict:
        market_research_report = state["market_report"]
        volume_flow_report = state["sentiment_report"]
        funding_oi_report = state["funding_oi_report"]
        news_report = state["news_report"]
        tokenomics_report = state["tokenomics_report"]
        investment_plan = state["investment_plan"]
        setup_classification = state["setup_classification"]
        decision_plan = state["decision_plan"]
        prompt = f"""As the Trade Risk Analyst, evaluate the risk quality of this single crypto trade idea.

Your scope is trade-level risk only. You are not the portfolio allocator and you do not send orders.

You must answer:
- Is the stop logical and tied to a real invalidation?
- Is the invalidation clear or vague?
- Is the reward-to-risk good enough?
- What is the maximum position size allowed for this setup?
- Are spread, slippage, volatility, or candle extension making execution unsafe?
- Should this trade be approved, constrained, delayed, or rejected?

Inputs:
- Research Manager verdict: {investment_plan}
- Setup Classifier output: {setup_classification}
- Decision Engine output: {decision_plan}
- Market structure report: {market_research_report}
- Volume flow report: {volume_flow_report}
- Funding and open interest report: {funding_oi_report}
- Crypto catalyst report: {news_report}
- Tokenomics and on-chain report: {tokenomics_report}

Required output structure:
1. Risk Status: approved / approved_with_constraints / wait / rejected
2. Max Position Size: normalized fraction from 0.0 to 1.0
3. Stop Distance Pct
4. Invalidation Quality: clear / acceptable / weak
5. Expected R Multiple
6. Execution Risk: low / medium / high
7. Constraints
8. Disqualifiers
9. Bottom Line

Hard rules:
- You can reject the trade. Do not reduce this role to size calculation.
- Do not override portfolio policy, total risk budget, or execution policy.
- If the setup has poor invalidation, weak reward-to-risk, or unsafe execution quality, say so directly.
- If the trade looks directionally right but structurally bad to execute now, prefer wait or rejected.
"""

        response = llm.invoke(prompt)
        return {"trade_risk_assessment": response.content}

    return trade_risk_node
