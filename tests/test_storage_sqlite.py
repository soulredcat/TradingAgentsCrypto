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

    def test_analysis_progress_snapshot_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "progress.sqlite3")
            repository = SQLiteRepository(db_path=db_path)
            run_id = repository.create_analysis_run(
                asset_symbol="ETH-PERP",
                timeframe="1h",
                analysis_time="2026-04-14 16:00",
            )

            repository.upsert_analysis_progress(
                run_id=run_id,
                selected_analysts=["market", "news"],
                agent_status={
                    "Market Structure Analyst": "completed",
                    "News Analyst": "in_progress",
                },
                report_sections={"market_report": "# market"},
                current_agent="News Analyst",
                current_report="### News\nloading",
                stats={"llm_calls": 3, "tool_calls": 2},
            )

            progress = repository.get_analysis_progress(run_id)
            runs = repository.list_analysis_runs(limit=5)

            self.assertIsNotNone(progress)
            self.assertEqual(progress["current_agent"], "News Analyst")
            self.assertEqual(progress["selected_analysts"], ["market", "news"])
            self.assertEqual(runs[0]["agent_status"]["News Analyst"], "in_progress")

    def test_monitoring_loop_round_trip_and_due_filter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "loops.sqlite3")
            repository = SQLiteRepository(db_path=db_path)

            loop_id = repository.create_monitoring_loop(
                asset_symbol="BTC-PERP",
                timeframe="1h",
                interval_minutes=10,
                selections={
                    "asset_symbol": "BTC-PERP",
                    "timeframe": "1h",
                    "analysis_date": "now",
                    "analysts": ["market", "news"],
                },
                next_run_at="2026-04-14T09:00:00+00:00",
            )

            due = repository.get_due_monitoring_loops(
                now_iso="2026-04-14T09:01:00+00:00"
            )
            self.assertEqual(len(due), 1)
            self.assertEqual(due[0]["id"], loop_id)

            run_id = repository.create_analysis_run(
                asset_symbol="BTC-PERP",
                timeframe="1h",
                analysis_time="2026-04-14 16:00",
            )
            repository.mark_monitoring_loop_run_started(loop_id, run_id)
            running_loop = repository.get_monitoring_loop(loop_id)
            self.assertEqual(running_loop["active_run_id"], run_id)

            repository.mark_monitoring_loop_run_finished(
                loop_id,
                run_status="completed",
                next_run_at="2026-04-14T09:20:00+00:00",
            )
            completed_loop = repository.get_monitoring_loop(loop_id)
            self.assertIsNone(completed_loop["active_run_id"])
            self.assertEqual(completed_loop["last_run_status"], "completed")
            self.assertEqual(
                completed_loop["next_run_at"], "2026-04-14T09:20:00+00:00"
            )

    def test_retention_prunes_old_completed_runs_per_asset_timeframe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "retention.sqlite3")
            repository = SQLiteRepository(
                db_path=db_path,
                config={
                    "storage_retention_days": 365,
                    "storage_max_runs_per_asset_timeframe": 2,
                    "storage_max_reflection_entries_per_memory": 300,
                },
            )

            for index in range(3):
                run_id = repository.create_analysis_run(
                    asset_symbol="BTC-PERP",
                    timeframe="1h",
                    analysis_time=f"2026-04-14 {index:02d}:00",
                )
                repository.update_analysis_run_status(run_id, "completed")

            remaining_runs = repository.list_analysis_runs(limit=10)

            self.assertEqual(len(remaining_runs), 2)
            self.assertEqual(
                [run["analysis_time"] for run in remaining_runs],
                ["2026-04-14 02:00", "2026-04-14 01:00"],
            )

    def test_retention_prunes_reflection_memory_entries_per_memory_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "memory-retention.sqlite3")
            repository = SQLiteRepository(
                db_path=db_path,
                config={
                    "storage_retention_days": 365,
                    "storage_max_runs_per_asset_timeframe": 240,
                    "storage_max_reflection_entries_per_memory": 2,
                },
            )

            repository.add_memory_entries(
                "bull_memory",
                [
                    ("s1", "r1"),
                    ("s2", "r2"),
                    ("s3", "r3"),
                ],
            )

            entries = repository.list_memory_entries("bull_memory")

            self.assertEqual(entries, [("s2", "r2"), ("s3", "r3")])


if __name__ == "__main__":
    unittest.main()
