import os
import tempfile
import unittest

from cli.message_buffer import MessageBuffer
from cli.reporting import attach_analysis_persistence
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.storage import SQLiteRepository


class SQLiteStorageTests(unittest.TestCase):
    def test_message_and_report_persistence_go_to_sqlite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "storage.sqlite3")
            repository = SQLiteRepository(db_path=db_path)
            run_id = repository.create_analysis_run(
                asset_symbol="BTC-PERP",
                timeframe="1h",
                analysis_time="2026-04-14 16:00",
            )

            message_buffer = MessageBuffer()
            message_buffer.init_for_analysis(["market", "news"])
            attach_analysis_persistence(message_buffer, repository=repository, run_id=run_id)

            message_buffer.add_message("System", "analysis started")
            message_buffer.add_tool_call("get_market_data", {"symbol": "BTC-PERP"})
            message_buffer.update_report_section("market_report", "# structure report")

            messages = repository.get_run_messages(run_id)
            tool_calls = repository.get_run_tool_calls(run_id)
            report_sections = repository.get_report_sections(run_id)

            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["message_type"], "System")
            self.assertEqual(len(tool_calls), 1)
            self.assertEqual(tool_calls[0]["tool_name"], "get_market_data")
            self.assertEqual(report_sections["market_report"], "# structure report")

    def test_profile_round_trip_uses_sqlite_store(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "profiles.sqlite3")
            profile_path = os.path.join(temp_dir, "profile.json")
            os.environ["TRADINGAGENTS_DB_PATH"] = db_path
            try:
                from cli.profile import load_profile, save_profile

                selections = {
                    "asset_symbol": "ETH-PERP",
                    "timeframe": "4h",
                    "analysis_date": "2026-04-14 16:00",
                    "analysts": [],
                    "research_depth": 1,
                    "llm_provider": "codex_exec",
                    "backend_url": None,
                    "shallow_thinker": "gpt-5.4-mini",
                    "deep_thinker": "gpt-5.4",
                    "google_thinking_level": None,
                    "openai_reasoning_effort": None,
                    "anthropic_effort": None,
                    "output_language": "English",
                }
                db_file = save_profile(selections, profile_path)
                loaded = load_profile(profile_path)
            finally:
                os.environ.pop("TRADINGAGENTS_DB_PATH", None)

            self.assertEqual(str(db_file), db_path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["asset_symbol"], "ETH-PERP")

    def test_reflection_memory_persists_and_reloads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "memory.sqlite3")
            config = {"storage_db_path": db_path}
            memory = FinancialSituationMemory("bull_memory", config=config)
            memory.add_situations([("btc reclaim with strong volume", "prefer continuation long")])

            reloaded = FinancialSituationMemory("bull_memory", config=config)
            memories = reloaded.get_memories("btc reclaim and volume expansion", n_matches=1)

            self.assertEqual(len(memories), 1)
            self.assertEqual(memories[0]["recommendation"], "prefer continuation long")

    def test_full_state_log_and_complete_report_are_persisted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "analysis.sqlite3")
            repository = SQLiteRepository(db_path=db_path)
            run_id = repository.create_analysis_run(
                asset_symbol="SOL-PERP",
                timeframe="1h",
                analysis_time="2026-04-14 16:00",
            )

            repository.save_full_state_log(
                trade_date="2026-04-14 16:00",
                payload={
                    "asset_symbol": "SOL-PERP",
                    "trader_investment_plan": "FINAL TRANSACTION PROPOSAL: **HOLD**",
                },
                run_id=run_id,
                asset_symbol="SOL-PERP",
            )
            repository.save_complete_report(
                run_id=run_id,
                asset_symbol="SOL-PERP",
                markdown="# Complete report",
            )

            full_state = repository.get_full_state_log(run_id)
            complete_report = repository.get_complete_report(run_id)

            self.assertEqual(
                full_state["trader_investment_plan"],
                "FINAL TRANSACTION PROPOSAL: **HOLD**",
            )
            self.assertEqual(complete_report, "# Complete report")


if __name__ == "__main__":
    unittest.main()
