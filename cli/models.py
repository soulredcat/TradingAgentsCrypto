from enum import Enum


class AnalystType(str, Enum):
    MARKET = "market"
    VOLUME_FLOW = "volume_flow"
    FUNDING_OI = "funding_oi"
    NEWS = "news"
    TOKENOMICS = "tokenomics"


ANALYST_LABELS = {
    AnalystType.MARKET: "Market Structure Analyst",
    AnalystType.VOLUME_FLOW: "Volume Flow Analyst",
    AnalystType.FUNDING_OI: "Funding & OI Analyst",
    AnalystType.NEWS: "News Analyst",
    AnalystType.TOKENOMICS: "Tokenomics & On-Chain Analyst",
}

ANALYST_ALIASES = {
    "market": AnalystType.MARKET,
    "market_analyst": AnalystType.MARKET,
    "market_structure": AnalystType.MARKET,
    "market_structure_analyst": AnalystType.MARKET,
    "volume_flow": AnalystType.VOLUME_FLOW,
    "volume_flow_analyst": AnalystType.VOLUME_FLOW,
    "sentiment": AnalystType.VOLUME_FLOW,
    "sentiment_analyst": AnalystType.VOLUME_FLOW,
    "funding_oi": AnalystType.FUNDING_OI,
    "funding_oi_analyst": AnalystType.FUNDING_OI,
    "funding": AnalystType.FUNDING_OI,
    "oi": AnalystType.FUNDING_OI,
    "derivatives": AnalystType.FUNDING_OI,
    "derivatives_analyst": AnalystType.FUNDING_OI,
    "news": AnalystType.NEWS,
    "news_analyst": AnalystType.NEWS,
    "catalyst_news": AnalystType.NEWS,
    "catalyst_news_analyst": AnalystType.NEWS,
    "event_news": AnalystType.NEWS,
    "event_news_analyst": AnalystType.NEWS,
    "tokenomics": AnalystType.TOKENOMICS,
    "tokenomics_analyst": AnalystType.TOKENOMICS,
    "tokenomics_onchain": AnalystType.TOKENOMICS,
    "tokenomics_onchain_analyst": AnalystType.TOKENOMICS,
}

PREFERRED_ANALYST_PROFILE_NAMES = {
    AnalystType.MARKET: "market_structure_analyst",
    AnalystType.VOLUME_FLOW: "volume_flow_analyst",
    AnalystType.FUNDING_OI: "funding_oi_analyst",
    AnalystType.NEWS: "news_analyst",
    AnalystType.TOKENOMICS: "tokenomics_onchain_analyst",
}


def normalize_analyst_type(value) -> AnalystType:
    if isinstance(value, AnalystType):
        return value
    raw_value = str(value).strip().lower()
    if raw_value in ANALYST_ALIASES:
        return ANALYST_ALIASES[raw_value]
    return AnalystType(raw_value)


def get_analyst_label(value) -> str:
    return ANALYST_LABELS[normalize_analyst_type(value)]


def serialize_analyst_type(value) -> str:
    return PREFERRED_ANALYST_PROFILE_NAMES[normalize_analyst_type(value)]
