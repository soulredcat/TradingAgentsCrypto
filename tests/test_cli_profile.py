import os
import json
import tempfile
import unittest
from pathlib import Path

from cli.models import AnalystType
from cli.profile import (
    build_selections_from_profile,
    format_analysis_date_for_path,
    get_today_analysis_date,
    load_profile,
    normalize_profile,
    save_profile,
)


class CliProfileTests(unittest.TestCase):
    def test_normalize_profile_falls_back_to_safe_defaults(self):
        profile = normalize_profile(
            {
                "asset_symbol": " hype-perp ",
                "timeframe": "12h",
                "analysis_date": "",
                "analysts": ["market", "invalid", "news"],
                "research_depth": 99,
                "llm_provider": "OpenAI",
            }
        )

        self.assertEqual(profile["asset_symbol"], "HYPE-PERP")
        self.assertEqual(profile["timeframe"], "1h")
        self.assertEqual(profile["analysis_date"], "now")
        self.assertEqual(profile["analysts"], ["market", "news"])
        self.assertEqual(profile["research_depth"], 1)
        self.assertEqual(profile["llm_provider"], "openai")

    def test_normalize_profile_accepts_market_structure_alias(self):
        profile = normalize_profile(
            {
                "asset_symbol": "BTC-PERP",
                "analysts": ["market_structure_analyst", "news"],
            }
        )

        self.assertEqual(profile["analysts"], ["market", "news"])

    def test_normalize_profile_maps_volume_flow_and_legacy_sentiment_aliases(self):
        profile = normalize_profile(
            {
                "asset_symbol": "BTC-PERP",
                "analysts": ["volume_flow_analyst", "sentiment", "news"],
            }
        )

        self.assertEqual(profile["analysts"], ["volume_flow", "news"])

    def test_normalize_profile_maps_funding_oi_aliases(self):
        profile = normalize_profile(
            {
                "asset_symbol": "BTC-PERP",
                "analysts": ["funding_oi_analyst", "derivatives", "news"],
            }
        )

        self.assertEqual(profile["analysts"], ["funding_oi", "news"])

    def test_normalize_profile_maps_catalyst_news_aliases(self):
        profile = normalize_profile(
            {
                "asset_symbol": "BTC-PERP",
                "analysts": ["catalyst_news_analyst", "event_news", "tokenomics"],
            }
        )

        self.assertEqual(profile["analysts"], ["news", "tokenomics"])

    def test_normalize_profile_maps_tokenomics_onchain_alias(self):
        profile = normalize_profile(
            {
                "asset_symbol": "BTC-PERP",
                "analysts": ["tokenomics_onchain_analyst", "news"],
            }
        )

        self.assertEqual(profile["analysts"], ["tokenomics", "news"])

    def test_build_selections_resolves_now_and_analyst_enums(self):
        selections = build_selections_from_profile(
            {
                "asset_symbol": "BTC-PERP",
                "timeframe": "4h",
                "analysis_date": "now",
                "analysts": ["market", "tokenomics"],
                "research_depth": 3,
                "llm_provider": "codex_exec",
                "shallow_thinker": "gpt-5.4-mini",
                "deep_thinker": "gpt-5.4",
            }
        )

        self.assertEqual(selections["timeframe"], "4h")
        self.assertEqual(selections["analysis_date"], get_today_analysis_date("4h"))
        self.assertEqual(
            selections["analysts"],
            [AnalystType.MARKET, AnalystType.TOKENOMICS],
        )

    def test_save_profile_persists_reusable_defaults(self):
        selections = {
            "asset_symbol": "ETH-PERP",
            "timeframe": "1d",
            "analysis_date": "2026-04-14",
            "analysts": [
                AnalystType.MARKET,
                AnalystType.VOLUME_FLOW,
                AnalystType.FUNDING_OI,
            ],
            "research_depth": 3,
            "llm_provider": "openai",
            "backend_url": "https://api.openai.com/v1",
            "shallow_thinker": "gpt-5.4-mini",
            "deep_thinker": "gpt-5.4",
            "google_thinking_level": None,
            "openai_reasoning_effort": "medium",
            "anthropic_effort": None,
            "output_language": "Indonesian",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["TRADINGAGENTS_DB_PATH"] = str(Path(temp_dir) / "profiles.sqlite3")
            profile_path = Path(temp_dir) / "profile.json"
            try:
                db_path = save_profile(selections, profile_path, analysis_date_value="now")
                loaded = load_profile(profile_path)
            finally:
                os.environ.pop("TRADINGAGENTS_DB_PATH", None)

        self.assertIsNotNone(loaded)
        self.assertEqual(db_path.name, "profiles.sqlite3")
        self.assertEqual(loaded["asset_symbol"], "ETH-PERP")
        self.assertEqual(loaded["timeframe"], "1d")
        self.assertEqual(loaded["analysis_date"], "now")
        self.assertEqual(
            loaded["analysts"],
            [
                "market_structure_analyst",
                "volume_flow_analyst",
                "funding_oi_analyst",
            ],
        )
        self.assertEqual(loaded["output_language"], "Indonesian")

    def test_default_profile_prefers_public_analyst_aliases(self):
        profile = normalize_profile(None)

        self.assertEqual(
            profile["analysts"],
            [
                "market_structure_analyst",
                "volume_flow_analyst",
                "funding_oi_analyst",
                "news_analyst",
                "tokenomics_onchain_analyst",
            ],
        )

    def test_save_profile_ignores_legacy_batch_fields(self):
        selections = build_selections_from_profile(
            {
                "asset_symbol": "BTC-PERP",
            }
        )
        selections["asset_symbol"] = "SOL-PERP"

        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["TRADINGAGENTS_DB_PATH"] = str(Path(temp_dir) / "profiles.sqlite3")
            profile_path = Path(temp_dir) / "profile.json"
            try:
                save_profile(
                    selections,
                    profile_path,
                    existing_profile={
                        "watchlist": ["BTC-PERP", "ETH-PERP"],
                        "run_watchlist_as_batch": True,
                    },
                )
                loaded = load_profile(profile_path)
            finally:
                os.environ.pop("TRADINGAGENTS_DB_PATH", None)

        self.assertEqual(loaded["asset_symbol"], "SOL-PERP")
        self.assertNotIn("watchlist", loaded)
        self.assertNotIn("run_watchlist_as_batch", loaded)

    def test_saved_profile_file_is_valid_json(self):
        selections = build_selections_from_profile(None)

        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["TRADINGAGENTS_DB_PATH"] = str(Path(temp_dir) / "profiles.sqlite3")
            profile_path = Path(temp_dir) / "profile.json"
            try:
                save_profile(selections, profile_path)
                loaded_json = load_profile(profile_path)
            finally:
                os.environ.pop("TRADINGAGENTS_DB_PATH", None)

        self.assertIsInstance(loaded_json, dict)
        self.assertEqual(loaded_json["timeframe"], "1h")
        self.assertEqual(loaded_json["analysis_date"], "now")
        self.assertNotIn("watchlist", loaded_json)
        self.assertNotIn("run_watchlist_as_batch", loaded_json)

    def test_analysis_time_path_segment_is_windows_safe(self):
        self.assertEqual(
            format_analysis_date_for_path("2026-04-14 07:45"),
            "2026-04-14_07-00",
        )
        self.assertEqual(
            format_analysis_date_for_path("2026-04-14 07:45", timeframe="1d"),
            "2026-04-14",
        )


if __name__ == "__main__":
    unittest.main()
