import os
import tempfile
import unittest
from datetime import datetime, timezone
import importlib

from fastapi.testclient import TestClient


class WebAppTests(unittest.TestCase):
    def test_runs_and_detail_pages_render_from_sqlite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "web.sqlite3")
            os.environ["TRADINGAGENTS_DB_PATH"] = db_path
            os.environ["TRADINGAGENTS_WEB_DISABLE_SCHEDULER"] = "1"
            try:
                from tradingagents.storage import SQLiteRepository
                from tradingagents.web.app import create_app

                repository = SQLiteRepository(db_path=db_path)
                run_id = repository.create_analysis_run(
                    asset_symbol="BTC-PERP",
                    timeframe="1h",
                    analysis_time="2026-04-14 16:00",
                )
                repository.upsert_analysis_progress(
                    run_id=run_id,
                    selected_analysts=["market", "volume_flow"],
                    agent_status={
                        "Market Structure Analyst": "completed",
                        "Volume Flow Analyst": "in_progress",
                        "Bull Researcher": "pending",
                    },
                    report_sections={"market_report": "# structure"},
                    current_agent="Volume Flow Analyst",
                    current_report="### Market Structure Analysis\n# structure",
                    stats={"llm_calls": 1, "tool_calls": 2},
                )
                repository.append_message(run_id, "16:00:01", "System", "analysis started")

                client = TestClient(create_app())
                runs_response = client.get("/runs")
                detail_response = client.get(f"/runs/{run_id}")
            finally:
                os.environ.pop("TRADINGAGENTS_DB_PATH", None)
                os.environ.pop("TRADINGAGENTS_WEB_DISABLE_SCHEDULER", None)

            self.assertEqual(runs_response.status_code, 200)
            self.assertIn("BTC-PERP", runs_response.text)
            self.assertIn("Live Output", runs_response.text)
            self.assertIn("analysis started", runs_response.text)
            self.assertEqual(detail_response.status_code, 200)
            self.assertIn("Volume Flow Analyst", detail_response.text)
            self.assertIn("analysis started", detail_response.text)

    def test_root_redirects_to_running_run_detail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "root.sqlite3")
            os.environ["TRADINGAGENTS_DB_PATH"] = db_path
            os.environ["TRADINGAGENTS_WEB_DISABLE_SCHEDULER"] = "1"
            try:
                from tradingagents.storage import SQLiteRepository
                from tradingagents.web.app import create_app

                repository = SQLiteRepository(db_path=db_path)
                run_id = repository.create_analysis_run(
                    asset_symbol="ETH-PERP",
                    timeframe="1h",
                    analysis_time="2026-04-14 16:00",
                    status="running",
                )
                repository.upsert_analysis_progress(
                    run_id=run_id,
                    selected_analysts=["market"],
                    agent_status={"Market Structure Analyst": "in_progress"},
                    report_sections={},
                    current_agent="Market Structure Analyst",
                    current_report=None,
                    stats={},
                )

                client = TestClient(create_app())
                response = client.get("/", follow_redirects=False)
            finally:
                os.environ.pop("TRADINGAGENTS_DB_PATH", None)
                os.environ.pop("TRADINGAGENTS_WEB_DISABLE_SCHEDULER", None)

            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers["location"], f"/runs/{run_id}")

    def test_runs_page_uses_websocket_when_active_run_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "runs-refresh.sqlite3")
            os.environ["TRADINGAGENTS_DB_PATH"] = db_path
            os.environ["TRADINGAGENTS_WEB_DISABLE_SCHEDULER"] = "1"
            try:
                from tradingagents.storage import SQLiteRepository
                from tradingagents.web.app import create_app

                repository = SQLiteRepository(db_path=db_path)
                run_id = repository.create_analysis_run(
                    asset_symbol="ETH-PERP",
                    timeframe="1h",
                    analysis_time="2026-04-14 16:00",
                    status="running",
                )
                repository.upsert_analysis_progress(
                    run_id=run_id,
                    selected_analysts=["market"],
                    agent_status={"Market Structure Analyst": "in_progress"},
                    report_sections={"market_report": "# live structure"},
                    current_agent="Market Structure Analyst",
                    current_report="### Market Structure Analysis\n# live structure",
                    stats={},
                )

                client = TestClient(create_app())
                response = client.get("/runs")
            finally:
                os.environ.pop("TRADINGAGENTS_DB_PATH", None)
                os.environ.pop("TRADINGAGENTS_WEB_DISABLE_SCHEDULER", None)

            self.assertEqual(response.status_code, 200)
            self.assertNotIn('http-equiv="refresh"', response.text)
            self.assertIn("/ws/runs/", response.text)
            self.assertIn("Live updates via WebSocket", response.text)
            self.assertIn("Market Structure Analyst", response.text)

    def test_run_live_websocket_streams_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "runs-websocket.sqlite3")
            os.environ["TRADINGAGENTS_DB_PATH"] = db_path
            os.environ["TRADINGAGENTS_WEB_DISABLE_SCHEDULER"] = "1"
            try:
                from tradingagents.storage import SQLiteRepository
                from tradingagents.web.app import create_app

                repository = SQLiteRepository(db_path=db_path)
                run_id = repository.create_analysis_run(
                    asset_symbol="ETH-PERP",
                    timeframe="1h",
                    analysis_time="2026-04-14 16:00",
                    status="running",
                )
                repository.upsert_analysis_progress(
                    run_id=run_id,
                    selected_analysts=["market"],
                    agent_status={"Market Structure Analyst": "in_progress"},
                    report_sections={"market_report": "# live structure"},
                    current_agent="Market Structure Analyst",
                    current_report="### Market Structure Analysis\n# live structure",
                    stats={},
                )
                repository.append_message(run_id, "16:00:01", "Data", "initial snapshot")

                client = TestClient(create_app())
                with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
                    payload = websocket.receive_json()
            finally:
                os.environ.pop("TRADINGAGENTS_DB_PATH", None)
                os.environ.pop("TRADINGAGENTS_WEB_DISABLE_SCHEDULER", None)

            self.assertEqual(payload["run"]["id"], run_id)
            self.assertEqual(payload["run"]["asset_symbol"], "ETH-PERP")
            self.assertEqual(payload["run"]["current_agent"], "Market Structure Analyst")
            self.assertEqual(payload["run"]["status"], "running")
            self.assertTrue(payload["is_running"])
            self.assertIn("live structure", payload["report_text"])
            self.assertEqual(payload["messages"][0]["content"], "initial snapshot")

    def test_loop_create_assigns_fixed_slots_and_removes_delete_action(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "loops.sqlite3")
            os.environ["TRADINGAGENTS_DB_PATH"] = db_path
            os.environ["TRADINGAGENTS_WEB_DISABLE_SCHEDULER"] = "1"
            original_utc_now = None
            try:
                from tradingagents.storage import SQLiteRepository
                web_app_module = importlib.import_module("tradingagents.web.app")

                fixed_now = datetime(2026, 4, 14, 16, 5, tzinfo=timezone.utc)
                original_utc_now = getattr(web_app_module, "_utc_now")
                web_app_module._utc_now = lambda: fixed_now

                client = TestClient(web_app_module.create_app())
                first_create_response = client.post(
                    "/loops",
                    data={
                        "asset_symbol": "ETH-PERP",
                        "timeframe": "1h",
                    },
                    follow_redirects=True,
                )
                second_create_response = client.post(
                    "/loops",
                    data={
                        "asset_symbol": "SOL-PERP",
                        "timeframe": "1h",
                    },
                    follow_redirects=True,
                )

                repository = SQLiteRepository(db_path=db_path)
                loops = repository.list_monitoring_loops()
                run_id = repository.create_analysis_run(
                    asset_symbol="ETH-PERP",
                    timeframe="1h",
                    analysis_time="2026-04-14 16:00",
                    status="completed",
                )
                repository.mark_monitoring_loop_run_started(loops[0]["id"], run_id)
                repository.mark_monitoring_loop_run_finished(
                    min(loop["id"] for loop in loops),
                    run_status="completed",
                    next_run_at="2026-04-14T17:00:00+00:00",
                )
                loops_page_response = client.get("/loops")
            finally:
                if "web_app_module" in locals() and original_utc_now is not None:
                    web_app_module._utc_now = original_utc_now
                os.environ.pop("TRADINGAGENTS_DB_PATH", None)
                os.environ.pop("TRADINGAGENTS_WEB_DISABLE_SCHEDULER", None)

            self.assertEqual(first_create_response.status_code, 200)
            self.assertEqual(second_create_response.status_code, 200)
            self.assertEqual(len(loops), 2)
            sorted_loops = sorted(loops, key=lambda item: item["id"])
            self.assertEqual(sorted_loops[0]["asset_symbol"], "ETH-PERP")
            self.assertEqual(sorted_loops[0]["next_run_at"], "2026-04-14T17:00:00+00:00")
            self.assertEqual(sorted_loops[1]["asset_symbol"], "SOL-PERP")
            self.assertEqual(sorted_loops[1]["next_run_at"], "2026-04-14T16:12:00+00:00")
            self.assertEqual(loops_page_response.status_code, 200)
            self.assertIn("Tracked pair priority", loops_page_response.text)
            self.assertIn("#1", loops_page_response.text)
            self.assertIn("ETH-PERP", loops_page_response.text)
            self.assertIn("Pair 1", loops_page_response.text)
            self.assertIn(":00", loops_page_response.text)
            self.assertIn("Pair 2", loops_page_response.text)
            self.assertIn(":12", loops_page_response.text)
            self.assertNotIn(">Delete<", loops_page_response.text)


if __name__ == "__main__":
    unittest.main()
