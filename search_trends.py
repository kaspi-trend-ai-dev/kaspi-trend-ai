"""Public Google Search trends for Kazakhstan, separate from Kaspi sales data."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
import re
from urllib.parse import urlencode
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
import requests


RSS_URL = "https://trends.google.com/trending/rss?geo=KZ"
SOURCE_NAME = "Google Trends"
CACHE_TTL_SECONDS = 900
MAX_FEED_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT = (5, 15)


class TrendSourceError(Exception):
    """The public source could not provide a usable RSS snapshot."""


@dataclass(frozen=True)
class SearchTrend:
    query: str
    traffic_label: str
    traffic_min: int | None
    published_at: datetime | None
    url: str


@dataclass(frozen=True)
class TrendSnapshot:
    trends: tuple[SearchTrend, ...]
    fetched_at: datetime
    source_url: str = RSS_URL


def _traffic_min(label: str) -> int | None:
    """Parse a volume bucket's lower bound, leaving unknown values unknown."""
    value = re.sub(r"\s+", "", label).lower()
    match = re.fullmatch(r"([0-9][0-9.,]*)(k|m|тыс\.?|млн\.?)?\+?", value)
    if not match:
        return None

    number, suffix = match.groups()
    if re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3})+", number):
        number = number.replace(",", "")
    elif "," in number:
        # Decimal commas are meaningful only with an explicit multiplier.
        if not suffix or not re.fullmatch(r"[0-9]+,[0-9]{1,2}", number):
            return None
        number = number.replace(",", ".")
    elif "." in number and not suffix:
        return None

    multiplier = 1
    if suffix in {"k", "тыс", "тыс."}:
        multiplier = 1_000
    elif suffix in {"m", "млн", "млн."}:
        multiplier = 1_000_000
    try:
        result = Decimal(number) * multiplier
        if not result.is_finite() or result != result.to_integral_value():
            return None
        return int(result)
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            return None
        return date.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def parse_trends_feed(xml: bytes) -> tuple[SearchTrend, ...]:
    """Parse RSS without interpreting its traffic buckets as sales or an index."""
    if len(xml) > MAX_FEED_BYTES:
        raise TrendSourceError("Ответ Google Trends слишком большой. Попробуйте обновить позже.")
    try:
        root = ElementTree.fromstring(
            xml, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except (ParseError, DefusedXmlException, ValueError, LookupError) as exc:
        raise TrendSourceError("Google Trends вернул некорректный RSS. Попробуйте позже.") from exc

    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise TrendSourceError("Google Trends вернул ответ без RSS-канала. Попробуйте позже.")

    trends = []
    seen = set()
    items = channel.findall("item")
    for item in items:
        query = " ".join((item.findtext("title") or "").split())
        if not query or query.casefold() in seen:
            continue
        seen.add(query.casefold())
        traffic_label = " ".join((item.findtext("{*}approx_traffic") or "").split())
        trends.append(
            SearchTrend(
                query=query,
                traffic_label=traffic_label,
                traffic_min=_traffic_min(traffic_label),
                published_at=_published_at(item.findtext("pubDate")),
                # Use a fixed Google host and encoded query, never an RSS-supplied link.
                url="https://trends.google.com/trends/explore?"
                + urlencode({"geo": "KZ", "q": query}),
            )
        )
    if items and not trends:
        raise TrendSourceError(
            "В RSS Google Trends нет корректных поисковых запросов. Попробуйте позже."
        )
    return tuple(trends)


def fetch_search_trends() -> TrendSnapshot:
    """Read the public KZ feed with bounded I/O; callers decide how to cache it."""
    try:
        with requests.get(
            RSS_URL,
            timeout=REQUEST_TIMEOUT,
            stream=True,
            allow_redirects=False,
            headers={
                "Accept": "application/rss+xml, application/xml, text/xml",
                "User-Agent": "KaspiTrendAI RSS reader",
            },
        ) as response:
            if response.status_code != 200:
                raise TrendSourceError(
                    f"Google Trends временно недоступен (HTTP {response.status_code}). "
                    "Попробуйте обновить позже."
                )
            body = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if len(body) + len(chunk) > MAX_FEED_BYTES:
                    raise TrendSourceError(
                        "Ответ Google Trends слишком большой. Попробуйте обновить позже."
                    )
                body.extend(chunk)
        trends = parse_trends_feed(bytes(body))
    except requests.Timeout as exc:
        raise TrendSourceError(
            "Google Trends не ответил вовремя. Попробуйте обновить позже."
        ) from exc
    except requests.RequestException as exc:
        raise TrendSourceError(
            "Не удалось подключиться к Google Trends. Проверьте доступ к интернету "
            "и попробуйте обновить позже."
        ) from exc

    return TrendSnapshot(trends=trends, fetched_at=datetime.now(timezone.utc))
