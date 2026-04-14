# TradingAgents/graph/signal_processing.py

import re
from typing import Any


class SignalProcessor:
    """Processes trading signals to extract actionable decisions."""

    VALID_RATINGS = ("BUY", "OVERWEIGHT", "HOLD", "UNDERWEIGHT", "SELL")

    def __init__(self, quick_thinking_llm: Any):
        """Initialize with an LLM for processing."""
        self.quick_thinking_llm = quick_thinking_llm

    def _normalize_rating(self, rating: str | None) -> str | None:
        """Normalize a parsed rating to the canonical uppercase label."""
        if not rating:
            return None

        normalized = rating.strip().upper()
        return normalized if normalized in self.VALID_RATINGS else None

    def _extract_rating_deterministically(self, full_signal: str) -> str | None:
        """Parse expected decision formats before falling back to the LLM."""
        if not full_signal:
            return None

        rating_match = re.search(
            r"Rating\s*:\s*(Buy|Overweight|Hold|Underweight|Sell)\b",
            full_signal,
            flags=re.IGNORECASE,
        )
        if rating_match:
            return self._normalize_rating(rating_match.group(1))

        proposal_match = re.search(
            r"FINAL TRANSACTION PROPOSAL\s*:\s*\*{0,2}\s*(BUY|HOLD|SELL)\s*\*{0,2}",
            full_signal,
            flags=re.IGNORECASE,
        )
        if proposal_match:
            return self._normalize_rating(proposal_match.group(1))

        for rating in self.VALID_RATINGS:
            if re.search(rf"\b{rating}\b", full_signal, flags=re.IGNORECASE):
                return rating

        return None

    def process_signal(self, full_signal: str) -> str:
        """
        Process a full trading signal to extract the core decision.

        Args:
            full_signal: Complete trading signal text

        Returns:
            Extracted rating (BUY, OVERWEIGHT, HOLD, UNDERWEIGHT, or SELL)
        """
        parsed_rating = self._extract_rating_deterministically(full_signal)
        if parsed_rating:
            return parsed_rating

        messages = [
            (
                "system",
                "You are an efficient assistant that extracts the trading decision from analyst reports. "
                "Extract the rating as exactly one of: BUY, OVERWEIGHT, HOLD, UNDERWEIGHT, SELL. "
                "Output only the single rating word, nothing else.",
            ),
            ("human", full_signal),
        ]

        llm_response = self.quick_thinking_llm.invoke(messages).content
        return self._normalize_rating(str(llm_response)) or str(llm_response).strip()
