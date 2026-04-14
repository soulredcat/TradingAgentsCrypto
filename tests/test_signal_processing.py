import unittest

from tradingagents.graph.signal_processing import SignalProcessor


class DummyResponse:
    def __init__(self, content: str):
        self.content = content


class DummyLLM:
    def __init__(self, content: str):
        self.content = content
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return DummyResponse(self.content)


class SignalProcessorTests(unittest.TestCase):
    def test_process_signal_parses_rating_without_llm(self):
        llm = DummyLLM("SELL")
        processor = SignalProcessor(llm)

        result = processor.process_signal(
            "Rating: Overweight\nExecutive Summary: Add slowly on pullbacks."
        )

        self.assertEqual(result, "OVERWEIGHT")
        self.assertEqual(llm.calls, 0)

    def test_process_signal_parses_final_transaction_proposal_without_llm(self):
        llm = DummyLLM("SELL")
        processor = SignalProcessor(llm)

        result = processor.process_signal(
            "Plan updated. FINAL TRANSACTION PROPOSAL: **BUY**"
        )

        self.assertEqual(result, "BUY")
        self.assertEqual(llm.calls, 0)

    def test_process_signal_falls_back_to_llm_when_text_has_no_parseable_rating(self):
        llm = DummyLLM("hold")
        processor = SignalProcessor(llm)

        result = processor.process_signal("No explicit decision string was provided here.")

        self.assertEqual(result, "HOLD")
        self.assertEqual(llm.calls, 1)


if __name__ == "__main__":
    unittest.main()
