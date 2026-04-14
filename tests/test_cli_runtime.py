import unittest

from cli.message_buffer import MessageBuffer
from cli.runtime import (
    DECISION_AGENT_NAMES,
    POST_DECISION_AGENT_NAMES,
    POST_EXECUTION_AGENT_NAMES,
    POST_PORTFOLIO_RISK_AGENT_NAMES,
    POST_RESEARCH_AGENT_NAMES,
    POST_TRADE_RISK_AGENT_NAMES,
    RESEARCH_AGENT_NAMES,
    analysts_phase_completed,
    decision_phase_completed,
    execution_phase_completed,
    portfolio_risk_phase_completed,
    set_agent_group_pending,
    trade_risk_phase_completed,
    update_analyst_statuses,
    update_research_debate_statuses,
)


class CliRuntimeStatusTests(unittest.TestCase):
    def setUp(self):
        self.message_buffer = MessageBuffer()
        self.message_buffer.init_for_analysis(["market"])

    def test_analyst_progress_does_not_start_research_team_early(self):
        update_analyst_statuses(self.message_buffer, {})

        self.assertEqual(
            self.message_buffer.agent_status["Market Structure Analyst"], "in_progress"
        )
        self.assertFalse(analysts_phase_completed(self.message_buffer))
        self.assertEqual(self.message_buffer.agent_status["Bull Researcher"], "pending")

        update_analyst_statuses(
            self.message_buffer,
            {"market_report": "Market Structure Analyst: report ready"},
        )

        self.assertEqual(
            self.message_buffer.agent_status["Market Structure Analyst"], "completed"
        )
        self.assertTrue(analysts_phase_completed(self.message_buffer))
        self.assertEqual(self.message_buffer.agent_status["Bull Researcher"], "pending")

    def test_analyst_progress_respects_funding_oi_order_before_news(self):
        self.message_buffer.init_for_analysis(["market", "volume_flow", "funding_oi", "news"])

        update_analyst_statuses(
            self.message_buffer,
            {
                "market_report": "done",
                "sentiment_report": "done",
            },
        )

        self.assertEqual(self.message_buffer.agent_status["Market Structure Analyst"], "completed")
        self.assertEqual(self.message_buffer.agent_status["Volume Flow Analyst"], "completed")
        self.assertEqual(self.message_buffer.agent_status["Funding & OI Analyst"], "in_progress")
        self.assertEqual(self.message_buffer.agent_status["News Analyst"], "pending")

    def test_phase_gate_can_force_later_teams_back_to_pending(self):
        self.message_buffer.update_agent_status("Bull Researcher", "in_progress")
        self.message_buffer.update_agent_status("Setup Classifier", "in_progress")
        self.message_buffer.update_agent_status("Trade Risk Analyst", "in_progress")
        self.message_buffer.update_agent_status("Portfolio Risk Analyst", "in_progress")
        self.message_buffer.update_agent_status("Execution Team", "in_progress")

        set_agent_group_pending(self.message_buffer, RESEARCH_AGENT_NAMES)
        set_agent_group_pending(self.message_buffer, DECISION_AGENT_NAMES)
        set_agent_group_pending(self.message_buffer, POST_DECISION_AGENT_NAMES)
        set_agent_group_pending(self.message_buffer, POST_RESEARCH_AGENT_NAMES)
        set_agent_group_pending(self.message_buffer, POST_TRADE_RISK_AGENT_NAMES)
        set_agent_group_pending(self.message_buffer, POST_PORTFOLIO_RISK_AGENT_NAMES)
        set_agent_group_pending(self.message_buffer, POST_EXECUTION_AGENT_NAMES)

        self.assertEqual(self.message_buffer.agent_status["Bull Researcher"], "pending")
        self.assertEqual(self.message_buffer.agent_status["Setup Classifier"], "pending")
        self.assertEqual(self.message_buffer.agent_status["Trade Risk Analyst"], "pending")
        self.assertEqual(self.message_buffer.agent_status["Portfolio Risk Analyst"], "pending")
        self.assertEqual(self.message_buffer.agent_status["Execution Team"], "pending")

    def test_decision_phase_only_completes_when_setup_classifier_finishes(self):
        self.assertFalse(decision_phase_completed(self.message_buffer))
        self.message_buffer.update_agent_status("Setup Classifier", "in_progress")
        self.assertFalse(decision_phase_completed(self.message_buffer))
        self.message_buffer.update_agent_status("Setup Classifier", "completed")
        self.assertFalse(decision_phase_completed(self.message_buffer))
        self.message_buffer.update_agent_status("Decision Engine", "in_progress")
        self.assertFalse(decision_phase_completed(self.message_buffer))
        self.message_buffer.update_agent_status("Decision Engine", "completed")
        self.assertTrue(decision_phase_completed(self.message_buffer))

    def test_trade_risk_phase_only_completes_when_trade_risk_analyst_finishes(self):
        self.assertFalse(trade_risk_phase_completed(self.message_buffer))
        self.message_buffer.update_agent_status("Trade Risk Analyst", "in_progress")
        self.assertFalse(trade_risk_phase_completed(self.message_buffer))
        self.message_buffer.update_agent_status("Trade Risk Analyst", "completed")
        self.assertTrue(trade_risk_phase_completed(self.message_buffer))

    def test_portfolio_risk_phase_only_completes_when_portfolio_risk_analyst_finishes(self):
        self.assertFalse(portfolio_risk_phase_completed(self.message_buffer))
        self.message_buffer.update_agent_status("Portfolio Risk Analyst", "in_progress")
        self.assertFalse(portfolio_risk_phase_completed(self.message_buffer))
        self.message_buffer.update_agent_status("Portfolio Risk Analyst", "completed")
        self.assertTrue(portfolio_risk_phase_completed(self.message_buffer))

    def test_execution_phase_only_completes_when_execution_team_finishes(self):
        self.assertFalse(execution_phase_completed(self.message_buffer))
        self.message_buffer.update_agent_status("Execution Team", "in_progress")
        self.assertFalse(execution_phase_completed(self.message_buffer))
        self.message_buffer.update_agent_status("Execution Team", "completed")
        self.assertTrue(execution_phase_completed(self.message_buffer))

    def test_research_team_marks_finished_turns_as_waiting_until_their_next_turn(self):
        update_research_debate_statuses(
            self.message_buffer,
            {
                "bull_history": "Bull Researcher: constructive setup",
                "bear_history": "",
                "current_response": "Bull Researcher: constructive setup",
                "judge_decision": "",
                "count": 1,
            },
            max_rounds=2,
        )

        self.assertEqual(self.message_buffer.agent_status["Bull Researcher"], "waiting")
        self.assertEqual(self.message_buffer.agent_status["Bear Researcher"], "in_progress")
        self.assertEqual(self.message_buffer.agent_status["Research Manager"], "pending")

    def test_research_team_marks_agents_completed_only_after_final_turn(self):
        update_research_debate_statuses(
            self.message_buffer,
            {
                "bull_history": "Bull 1\nBull 2",
                "bear_history": "Bear 1",
                "current_response": "Bull Researcher: final rebuttal",
                "judge_decision": "",
                "count": 3,
            },
            max_rounds=2,
        )

        self.assertEqual(self.message_buffer.agent_status["Bull Researcher"], "completed")
        self.assertEqual(self.message_buffer.agent_status["Bear Researcher"], "in_progress")
        self.assertEqual(self.message_buffer.agent_status["Research Manager"], "pending")

    def test_research_manager_only_completes_after_judgement_exists(self):
        update_research_debate_statuses(
            self.message_buffer,
            {
                "bull_history": "Bull 1\nBull 2",
                "bear_history": "Bear 1\nBear 2",
                "current_response": "Bear Researcher: final rebuttal",
                "judge_decision": "",
                "count": 4,
            },
            max_rounds=2,
        )

        self.assertEqual(self.message_buffer.agent_status["Bull Researcher"], "completed")
        self.assertEqual(self.message_buffer.agent_status["Bear Researcher"], "completed")
        self.assertEqual(self.message_buffer.agent_status["Research Manager"], "in_progress")

        update_research_debate_statuses(
            self.message_buffer,
            {
                "bull_history": "Bull 1\nBull 2",
                "bear_history": "Bear 1\nBear 2",
                "current_response": "Research Manager: decision",
                "judge_decision": "Hold with defined risk.",
                "count": 4,
            },
            max_rounds=2,
        )

        self.assertEqual(self.message_buffer.agent_status["Research Manager"], "completed")

if __name__ == "__main__":
    unittest.main()
