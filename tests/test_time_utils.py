import unittest
from datetime import datetime, timedelta

from tradingagents.time_utils import (
    current_analysis_time,
    format_series_timestamp,
    format_time_for_path,
    normalize_timeframe,
    parse_analysis_time,
    resolve_analysis_time,
    timeframe_to_timedelta,
)


class TimeUtilsTests(unittest.TestCase):
    def test_parse_analysis_time_accepts_date_only(self):
        parsed = parse_analysis_time("2026-04-14")
        self.assertEqual(parsed, datetime(2026, 4, 14, 0, 0))

    def test_resolve_analysis_time_normalizes_to_hour(self):
        self.assertEqual(
            resolve_analysis_time("2026-04-14 07:45"),
            "2026-04-14 07:00",
        )
        self.assertEqual(
            resolve_analysis_time("2026-04-14 07:45", timeframe="4h"),
            "2026-04-14 04:00",
        )
        self.assertEqual(
            resolve_analysis_time("2026-04-14 07:45", timeframe="1d"),
            "2026-04-14",
        )

    def test_format_time_for_path_is_windows_safe(self):
        self.assertEqual(
            format_time_for_path("2026-04-14 07:45"),
            "2026-04-14_07-00",
        )
        self.assertEqual(
            format_time_for_path("2026-04-14 07:45", timeframe="1d"),
            "2026-04-14",
        )

    def test_timeframe_helpers(self):
        self.assertEqual(timeframe_to_timedelta("1h"), timedelta(hours=1))
        self.assertEqual(timeframe_to_timedelta("4h"), timedelta(hours=4))
        self.assertEqual(timeframe_to_timedelta("1d"), timedelta(days=1))
        self.assertEqual(normalize_timeframe("4H"), "4h")
        self.assertEqual(
            format_series_timestamp(datetime(2026, 4, 14, 7, 0), "1h"),
            "2026-04-14 07:00",
        )
        self.assertEqual(
            format_series_timestamp(datetime(2026, 4, 14, 7, 0), "1d"),
            "2026-04-14",
        )

    def test_current_analysis_time_is_hour_aligned(self):
        current = current_analysis_time(datetime(2026, 4, 14, 7, 45, 33))
        self.assertEqual(current, "2026-04-14 07:00")
        self.assertEqual(
            current_analysis_time(datetime(2026, 4, 14, 7, 45, 33), timeframe="4h"),
            "2026-04-14 04:00",
        )
        self.assertEqual(
            current_analysis_time(datetime(2026, 4, 14, 7, 45, 33), timeframe="1d"),
            "2026-04-14",
        )


if __name__ == "__main__":
    unittest.main()
