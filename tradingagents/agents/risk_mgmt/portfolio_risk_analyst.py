def create_portfolio_risk_analyst(llm):
    def portfolio_risk_node(state) -> dict:
        market_research_report = state["market_report"]
        volume_flow_report = state["sentiment_report"]
        funding_oi_report = state["funding_oi_report"]
        news_report = state["news_report"]
        tokenomics_report = state["tokenomics_report"]
        investment_plan = state["investment_plan"]
        setup_classification = state["setup_classification"]
        decision_plan = state["decision_plan"]
        trade_risk_assessment = state.get("trade_risk_assessment", "")

        prompt = f"""As the Portfolio Risk Analyst, evaluate portfolio-level risk for adding this crypto trade candidate.

Your scope is portfolio or basket risk, not single-trade stop placement and not final order execution.

You must answer:
- If this trade is added, what happens to total portfolio exposure?
- Is the portfolio becoming too concentrated in one theme, one side, or one correlation cluster?
- Is there too much shared beta to BTC or broad crypto risk?
- Does this candidate overlap with existing or likely simultaneous positions?
- Does aggregate drawdown sensitivity still look acceptable?
- Should this candidate be approved, capped, reduced, delayed, or rejected at the portfolio level?

Available inputs:
- Research Manager verdict: {investment_plan}
- Setup Classifier output: {setup_classification}
- Decision Engine output: {decision_plan}
- Trade Risk Analyst assessment: {trade_risk_assessment}
- Market structure report: {market_research_report}
- Volume flow report: {volume_flow_report}
- Funding and open interest report: {funding_oi_report}
- Crypto catalyst report: {news_report}
- Tokenomics and on-chain report: {tokenomics_report}

Important limitations:
- If open positions, correlation data, leverage budget, or hard portfolio limits are not provided, say they are unavailable.
- Do not invent holdings, exposure caps, or portfolio policy.
- Do not override hard rejections from the Trade Risk Analyst.

Required output structure:
1. Portfolio Risk Status: approved / approved_with_reduction / wait / rejected / unavailable
2. Cluster Exposure
3. Correlation Warning: true / false / unavailable
4. BTC Beta Warning: low / medium / high / unavailable
5. Capital Allocation Cap: normalized fraction from 0.0 to 1.0 or unavailable
6. Allow Additional Position: true / false / unavailable
7. Required Reduction Before Entry
8. Required Actions
9. Disqualifiers
10. Bottom Line

Hard rules:
- You can reject the candidate at portfolio level.
- Do not reduce this role to generic diversification talk.
- Do not send orders and do not replace the Execution Team.
- If portfolio context is missing, be explicit about what cannot be validated.
"""

        response = llm.invoke(prompt)
        return {"portfolio_risk_assessment": response.content}

    return portfolio_risk_node
