import unittest

from cli.message_buffer import MessageBuffer
from tradingagents.agents.managers.decision_engine import create_decision_engine
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.managers.setup_classifier import create_setup_classifier
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.portfolio_risk_analyst import create_portfolio_risk_analyst
from tradingagents.agents.risk_mgmt.trade_risk_analyst import create_trade_risk_analyst


class DummyMemory:
    def get_memories(self, curr_situation, n_matches=2):
        return [{"recommendation": "Respect invalidation and avoid crowded entries."}]


class DummyResponse:
    def __init__(self, content):
        self.content = content


class CaptureLLM:
    def __init__(self, content):
        self.content = content
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return DummyResponse(self.content)


def build_state():
    return {
        "asset_symbol": "ETH-PERP",
        "market_report": "Structure bias bullish but higher timeframe still contested.",
        "sentiment_report": "Breakout quality confirmed with expanding participation.",
        "funding_oi_report": "Price up and OI up with moderate funding.",
        "news_report": "Futures launch is a mixed but relevant catalyst.",
        "tokenomics_report": "No immediate unlock but exchange inflows need watching.",
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "Bear Researcher: crowded positioning risk.",
            "count": 0,
        },
        "investment_plan": "",
        "setup_classification": "",
        "decision_plan": "",
        "trader_investment_plan": "",
        "trade_risk_assessment": "",
        "portfolio_risk_assessment": "",
    }


class ResearchRolePromptTests(unittest.TestCase):
    def test_bull_researcher_uses_structured_bull_contract(self):
        llm = CaptureLLM("Bull Thesis Summary\nConfidence: medium")
        node = create_bull_researcher(llm, DummyMemory())

        result = node(build_state())
        prompt = llm.prompts[-1]

        self.assertIn("Required output structure:", prompt)
        self.assertIn("Bull Thesis Summary", prompt)
        self.assertIn("Evidence List", prompt)
        self.assertIn("Confirm Conditions", prompt)
        self.assertIn("Invalidation Conditions", prompt)
        self.assertTrue(
            result["investment_debate_state"]["current_response"].startswith(
                "Bull Researcher:"
            )
        )

    def test_bear_researcher_uses_structured_bear_contract(self):
        llm = CaptureLLM("Bear Thesis Summary\nConfidence: medium")
        node = create_bear_researcher(llm, DummyMemory())

        state = build_state()
        state["investment_debate_state"]["current_response"] = (
            "Bull Researcher: reclaim is constructive."
        )
        result = node(state)
        prompt = llm.prompts[-1]

        self.assertIn("Required output structure:", prompt)
        self.assertIn("Bear Thesis Summary", prompt)
        self.assertIn("Failure Conditions", prompt)
        self.assertIn("Downside Triggers", prompt)
        self.assertIn("Trap Risk", prompt)
        self.assertTrue(
            result["investment_debate_state"]["current_response"].startswith(
                "Bear Researcher:"
            )
        )

    def test_research_manager_uses_verdict_contract_not_buy_sell_hold_contract(self):
        llm = CaptureLLM("Base Case\nNet Bias: mildly bullish")
        node = create_research_manager(llm, DummyMemory())

        state = build_state()
        state["investment_debate_state"]["history"] = (
            "Bull Researcher: constructive reclaim.\n"
            "Bear Researcher: crowded long risk."
        )
        result = node(state)
        prompt = llm.prompts[-1]

        self.assertIn("Required output structure:", prompt)
        self.assertIn("Base Case", prompt)
        self.assertIn("Alternative Case", prompt)
        self.assertIn("Tradeability", prompt)
        self.assertIn("Recommendation To Decision Layer", prompt)
        self.assertIn(
            "Do not turn this into a portfolio action like Buy / Sell / Hold",
            prompt,
        )
        self.assertEqual(result["investment_plan"], "Base Case\nNet Bias: mildly bullish")

    def test_setup_classifier_uses_tradeability_contract_not_execution_contract(self):
        llm = CaptureLLM("Setup Type: reclaim\nTradeable: true")
        node = create_setup_classifier(llm)

        state = build_state()
        state["investment_plan"] = "Net Bias: mildly bullish\nTradeability: medium"
        result = node(state)
        prompt = llm.prompts[-1]

        self.assertIn("Allowed setup types:", prompt)
        self.assertIn("Tradeable", prompt)
        self.assertIn("Reason If Not Tradeable", prompt)
        self.assertIn(
            "Do not overlap with trader or portfolio manager responsibilities",
            prompt,
        )
        self.assertEqual(
            result["setup_classification"], "Setup Type: reclaim\nTradeable: true"
        )

    def test_decision_engine_respects_setup_gating_and_risk_handoff_contract(self):
        llm = CaptureLLM("Decision: wait\nForward To Risk: false")
        node = create_decision_engine(llm)

        state = build_state()
        state["investment_plan"] = "Net Bias: mildly bullish\nTradeability: medium"
        state["setup_classification"] = "Setup Type: reclaim\nTradeable: false"
        result = node(state)
        prompt = llm.prompts[-1]

        self.assertIn("Allowed decisions:", prompt)
        self.assertIn("Do not force entry if the setup classifier says the setup is not tradeable", prompt)
        self.assertIn("Forward To Risk", prompt)
        self.assertIn("Blocking Factors", prompt)
        self.assertEqual(result["decision_plan"], "Decision: wait\nForward To Risk: false")

    def test_trade_risk_analyst_can_reject_trade_not_only_resize_it(self):
        llm = CaptureLLM("Risk Status: rejected\nDisqualifiers: reward-to-risk too poor")
        node = create_trade_risk_analyst(llm)

        state = build_state()
        state["investment_plan"] = "Net Bias: mildly bullish\nTradeability: medium"
        state["setup_classification"] = "Setup Type: reclaim\nTradeable: true"
        state["decision_plan"] = "Decision: wait\nForward To Risk: true"
        result = node(state)
        prompt = llm.prompts[-1]

        self.assertIn("trade-level risk only", prompt)
        self.assertIn("Risk Status: approved / approved_with_constraints / wait / rejected", prompt)
        self.assertIn("You can reject the trade", prompt)
        self.assertIn("Expected R Multiple", prompt)
        self.assertNotIn("Trader proposal", prompt)
        self.assertEqual(
            result["trade_risk_assessment"],
            "Risk Status: rejected\nDisqualifiers: reward-to-risk too poor",
        )

    def test_portfolio_risk_analyst_can_flag_cluster_and_correlation_risk(self):
        llm = CaptureLLM(
            "Portfolio Risk Status: approved_with_reduction\nCorrelation Warning: true"
        )
        node = create_portfolio_risk_analyst(llm)

        state = build_state()
        state["decision_plan"] = "Decision: long\nForward To Risk: true"
        state["trade_risk_assessment"] = "Risk Status: approved_with_constraints"
        result = node(state)
        prompt = llm.prompts[-1]

        self.assertIn("portfolio or basket risk", prompt)
        self.assertIn("Do not invent holdings, exposure caps, or portfolio policy", prompt)
        self.assertIn(
            "Portfolio Risk Status: approved / approved_with_reduction / wait / rejected / unavailable",
            prompt,
        )
        self.assertIn("Correlation Warning", prompt)
        self.assertEqual(
            result["portfolio_risk_assessment"],
            "Portfolio Risk Status: approved_with_reduction\nCorrelation Warning: true",
        )

    def test_execution_team_uses_portfolio_risk_assessment_not_debate_history(self):
        llm = CaptureLLM("FINAL TRANSACTION PROPOSAL: **HOLD**")
        from tradingagents.agents.trader.trader import create_trader

        node = create_trader(llm, DummyMemory())

        state = build_state()
        state["investment_plan"] = "Net Bias: mildly bullish"
        state["setup_classification"] = "Setup Type: reclaim\nTradeable: true"
        state["decision_plan"] = "Decision: long\nForward To Risk: true"
        state["trade_risk_assessment"] = "Risk Status: approved_with_constraints"
        state["portfolio_risk_assessment"] = "Portfolio Risk Status: approved_with_reduction"
        result = node(state)
        prompt = "\n".join(message["content"] for message in llm.prompts[-1])

        self.assertIn("Portfolio Risk Analyst assessment", prompt)
        self.assertNotIn("Risk analysts debate history", prompt)
        self.assertEqual(
            result["trader_investment_plan"],
            "FINAL TRANSACTION PROPOSAL: **HOLD**",
        )


class MessageBufferResearchVerdictTests(unittest.TestCase):
    def test_current_report_tracks_latest_section_while_final_report_keeps_full_flow(self):
        message_buffer = MessageBuffer()
        message_buffer.init_for_analysis(["market"])

        message_buffer.update_report_section(
            "investment_plan", "### Research Verdict\nNet Bias: mildly bullish"
        )
        message_buffer.update_report_section(
            "setup_classification", "### Setup Type\nreclaim"
        )
        message_buffer.update_report_section(
            "decision_plan", "### Decision\nwait"
        )

        self.assertIn("### Decision Team Formal Decision", message_buffer.current_report)
        self.assertIn("## Research Team Verdict", message_buffer.final_report)
        self.assertIn("## Decision Team Setup Classification", message_buffer.final_report)
        self.assertIn("## Decision Team Formal Decision", message_buffer.final_report)
        self.assertNotIn("## Trading Team Plan", message_buffer.final_report)


if __name__ == "__main__":
    unittest.main()
