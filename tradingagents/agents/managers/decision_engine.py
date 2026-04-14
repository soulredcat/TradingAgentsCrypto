def create_decision_engine(llm):
    def decision_engine_node(state) -> dict:
        asset_symbol = state["asset_symbol"]
        market_research_report = state["market_report"]
        volume_flow_report = state["sentiment_report"]
        funding_oi_report = state["funding_oi_report"]
        news_report = state["news_report"]
        tokenomics_report = state["tokenomics_report"]
        research_verdict = state["investment_plan"]
        setup_classification = state["setup_classification"]

        prompt = f"""You are the Decision Engine for a crypto trading desk.

Your job is to convert signal context, the structured research verdict, and the setup classification into a formal decision-layer recommendation.

You must answer:
- What action is most appropriate right now?
- Why does that action fit the evidence?
- How confident is the decision?
- How high is this candidate's priority?
- Should this idea be forwarded to the risk layer?

Allowed decisions:
- long
- short
- wait
- no-trade
- reduce
- exit

Important hard limits:
- Do not override hard policy, risk budget, or portfolio constraints.
- Do not force entry if the setup classifier says the setup is not tradeable.
- Do not send orders or act like execution is your responsibility.
- If the setup is valid but incomplete, prefer wait over forcing conviction.
- If the evidence is blurry, say no-trade clearly.

Priority guidance:
- Use 1 for highest priority.
- Use higher numbers for weaker or less urgent candidates.
- If there are no other candidates in context, still assign a priority based on setup cleanliness and urgency.

Required output structure:
1. Decision
2. Decision Confidence
3. Decision Reasoning
4. Priority
5. Candidate Status
6. Forward To Risk
7. Conditions To Proceed
8. Blocking Factors

Context for {asset_symbol}:
Market structure report: {market_research_report}
Volume flow report: {volume_flow_report}
Funding and open interest report: {funding_oi_report}
Crypto catalyst report: {news_report}
Tokenomics and on-chain report: {tokenomics_report}
Research Manager verdict: {research_verdict}
Setup Classifier output: {setup_classification}"""

        response = llm.invoke(prompt)
        return {"decision_plan": response.content}

    return decision_engine_node
