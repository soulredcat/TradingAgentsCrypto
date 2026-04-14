import unittest

from tradingagents.dataflows.providers.crypto_common import extract_base_asset, normalize_pair


class CryptoSymbolFormatTests(unittest.TestCase):
    def test_extract_base_asset_handles_hyperliquid_perp_suffix(self):
        self.assertEqual(extract_base_asset("BTC-PERP"), "BTC")
        self.assertEqual(extract_base_asset("HYPE-PERP"), "HYPE")

    def test_normalize_pair_maps_perp_to_binance_style_fallback(self):
        self.assertEqual(normalize_pair("BTC-PERP"), "BTCUSDT")
        self.assertEqual(normalize_pair("HYPE-PERP"), "HYPEUSDT")


if __name__ == "__main__":
    unittest.main()
