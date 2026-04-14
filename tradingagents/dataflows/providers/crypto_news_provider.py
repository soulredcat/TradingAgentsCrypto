from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional
from urllib.parse import quote_plus
from xml.etree import ElementTree

import requests

from .crypto_common import extract_base_asset, requests_verify_ssl
from tradingagents.dataflows.config import get_config
from tradingagents.time_utils import parse_analysis_time, resolve_analysis_time, timeframe_to_timedelta


GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}"


def _fetch_rss(query: str) -> ElementTree.Element:
    response = requests.get(
        GOOGLE_NEWS_RSS.format(query=quote_plus(query)),
        timeout=20,
        headers={"Accept": "application/xml"},
        verify=requests_verify_ssl(),
    )
    response.raise_for_status()
    return ElementTree.fromstring(response.content)


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return _normalize_datetime(parsedate_to_datetime(value))
    except (TypeError, ValueError):
        return None


def _normalize_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _collect_items(root: ElementTree.Element, limit: int, start_dt: Optional[datetime], end_dt: Optional[datetime]) -> List[str]:
    items: List[str] = []
    for item in root.findall("./channel/item"):
        pub_date = _parse_date(item.findtext("pubDate"))
        if start_dt and pub_date and pub_date < start_dt:
            continue
        if end_dt and pub_date and pub_date > end_dt:
            continue

        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source = item.findtext("source") or "Unknown source"
        published = pub_date.strftime("%Y-%m-%d %H:%M:%S %Z") if pub_date else "Unknown date"
        items.append(f"- {title}\n  source: {source}\n  published: {published}\n  link: {link}")
        if len(items) >= limit:
            break
    return items


def get_asset_news(asset_symbol: str, start_date: str, end_date: str) -> str:
    """Fetch asset-specific crypto news through Google News RSS."""
    timeframe = str(get_config().get("timeframe", "1h"))
    try:
        base_asset = extract_base_asset(asset_symbol)
        timeframe_delta = timeframe_to_timedelta(timeframe)
        start_dt = _normalize_datetime(parse_analysis_time(start_date, timeframe=timeframe))
        end_dt = _normalize_datetime(parse_analysis_time(end_date, timeframe=timeframe) + timeframe_delta)
        query = f'"{base_asset}" crypto OR token OR blockchain OR exchange'
        root = _fetch_rss(query)
        items = _collect_items(root, limit=10, start_dt=start_dt, end_dt=end_dt)
    except (ValueError, requests.RequestException, ElementTree.ParseError, TypeError) as exc:
        return f"Google News crypto asset feed unavailable for {asset_symbol}: {exc}"

    if not items:
        return f"No crypto news found for '{base_asset}' between {start_date} and {end_date}."

    return (
        f"# Crypto news for {base_asset}\n"
        f"# Window: {resolve_analysis_time(start_date, timeframe=timeframe)} to {resolve_analysis_time(end_date, timeframe=timeframe)}\n\n"
        + "\n\n".join(items)
    )


def get_market_news(curr_date: str, look_back_days: int = 7, limit: int = 5) -> str:
    """Fetch broad crypto market news for the recent lookback window."""
    timeframe = str(get_config().get("timeframe", "1h"))
    try:
        timeframe_delta = timeframe_to_timedelta(timeframe)
        end_dt = _normalize_datetime(parse_analysis_time(curr_date, timeframe=timeframe) + timeframe_delta)
        start_dt = end_dt - timedelta(days=look_back_days)
        query = "crypto market OR bitcoin OR ethereum OR stablecoin OR defi OR ETF"
        root = _fetch_rss(query)
        items = _collect_items(root, limit=limit, start_dt=start_dt, end_dt=end_dt)
    except (ValueError, requests.RequestException, ElementTree.ParseError, TypeError) as exc:
        return f"Google News crypto market feed unavailable for {curr_date}: {exc}"

    if not items:
        return f"No broad crypto market news found for window ending {curr_date}."

    return (
        f"# Crypto market news\n"
        f"# Window: {resolve_analysis_time(start_dt, timeframe=timeframe)} to {resolve_analysis_time(curr_date, timeframe=timeframe)}\n\n"
        + "\n\n".join(items)
    )
