from enum import Enum


class AnalystType(str, Enum):
    MARKET = "market"
    SENTIMENT = "sentiment"
    NEWS = "news"
    TOKENOMICS = "tokenomics"
