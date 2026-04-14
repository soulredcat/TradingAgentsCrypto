import json
import tempfile
import unittest
from pathlib import Path

from cli.models import AnalystType
from cli.profile import (
    build_selections_from_profile,
    get_today_analysis_date,
    load_profile,
    normalize_profile,
    save_profile,
)


class CliProfileTests(unittest.TestCase):
    def test_normalize_profile_falls_back_to_safe_defaults(self):
        profile = normalize_profile(
            {
                "asset_symbol": " suiusdt ",
                "analysis_date": "",
                "analysts": ["market", "invalid", "news"],
                "research_depth": 99,
                "llm_provider": "OpenAI",
            }
        )

        self.assertEqual(profile["asset_symbol"], "SUIUSDT")
        self.assertEqual(profile["analysis_date"], "today")
        self.assertEqual(profile["analysts"], ["market", "news"])
        self.assertEqual(profile["research_depth"], 1)
        self.assertEqual(profile["llm_provider"], "openai")

    def test_build_selections_resolves_today_and_analyst_enums(self):
        selections = build_selections_from_profile(
            {
                "asset_symbol": "BTCUSDT",
                "analysis_date": "today",
                "analysts": ["market", "tokenomics"],
                "research_depth": 3,
                "llm_provider": "codex_exec",
                "shallow_thinker": "gpt-5.4-mini",
                "deep_thinker": "gpt-5.4",
            }
        )

        self.assertEqual(selections["analysis_date"], get_today_analysis_date())
        self.assertEqual(
            selections["analysts"],
            [AnalystType.MARKET, AnalystType.TOKENOMICS],
        )

    def test_save_profile_persists_reusable_defaults(self):
        selections = {
            "asset_symbol": "ETHUSDT",
            "analysis_date": "2026-04-14",
            "analysts": [AnalystType.MARKET, AnalystType.SENTIMENT],
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
            profile_path = Path(temp_dir) / "profile.json"
            save_profile(selections, profile_path, analysis_date_value="today")
            loaded = load_profile(profile_path)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["asset_symbol"], "ETHUSDT")
        self.assertEqual(loaded["analysis_date"], "today")
        self.assertEqual(loaded["analysts"], ["market", "sentiment"])
        self.assertEqual(loaded["output_language"], "Indonesian")

    def test_saved_profile_file_is_valid_json(self):
        selections = build_selections_from_profile(None)

        with tempfile.TemporaryDirectory() as temp_dir:
            profile_path = Path(temp_dir) / "profile.json"
            save_profile(selections, profile_path)
            loaded_json = json.loads(profile_path.read_text(encoding="utf-8"))

        self.assertIsInstance(loaded_json, dict)
        self.assertEqual(loaded_json["analysis_date"], "today")


if __name__ == "__main__":
    unittest.main()
