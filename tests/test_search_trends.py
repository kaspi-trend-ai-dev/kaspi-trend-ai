"""Deterministic source contract checks; no live Google requests are made."""

from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import requests

from search_trends import (
    MAX_FEED_BYTES,
    REQUEST_TIMEOUT,
    RSS_URL,
    TrendSourceError,
    fetch_search_trends,
    parse_trends_feed,
)


def feed(items: str = "") -> bytes:
    return (
        '<rss version="2.0" xmlns:ht="https://trends.google.com/trending/rss">'
        f"<channel><title>Daily Search Trends</title>{items}</channel></rss>"
    ).encode("utf-8")


class ParseTrendsTests(unittest.TestCase):
    def test_namespace_traffic_date_and_safe_kazakhstan_url(self):
        trends = parse_trends_feed(feed(
            "<item><title>Телефон &amp; часы</title>"
            "<ht:approx_traffic>1,000+</ht:approx_traffic>"
            "<pubDate>Wed, 21 Oct 2026 15:00:00 +0500</pubDate>"
            "<link>javascript:alert(1)</link></item>"
        ))
        self.assertEqual(len(trends), 1)
        trend = trends[0]
        self.assertEqual(trend.query, "Телефон & часы")
        self.assertEqual(trend.traffic_label, "1,000+")
        self.assertEqual(trend.traffic_min, 1000)
        self.assertEqual(
            trend.published_at, datetime(2026, 10, 21, 10, tzinfo=timezone.utc)
        )
        url = urlparse(trend.url)
        self.assertEqual(url.scheme, "https")
        self.assertEqual(url.netloc, "trends.google.com")
        self.assertEqual(parse_qs(url.query), {"geo": ["KZ"], "q": [trend.query]})

    def test_traffic_buckets_and_unknown_values(self):
        cases = {
            "1K+": 1000,
            "10 тыс.+": 10_000,
            "1.5M+": 1_500_000,
            "1,5 тыс.+": 1500,
            "20\u202f000+": 20_000,
            "Unavailable": None,
            "": None,
            "1,2,3+": None,
            "-100": None,
        }
        for label, expected in cases.items():
            with self.subTest(label=label):
                result = parse_trends_feed(feed(
                    f"<item><title>query</title><ht:approx_traffic>{label}"
                    "</ht:approx_traffic></item>"
                ))
                self.assertEqual(result[0].traffic_min, expected)

    def test_empty_channel_is_a_valid_empty_result(self):
        self.assertEqual(parse_trends_feed(feed()), ())

    def test_items_without_any_usable_query_are_an_invalid_feed(self):
        with self.assertRaises(TrendSourceError):
            parse_trends_feed(feed("<item/><item><title> </title></item>"))

    def test_handles_provider_namespace_changes(self):
        xml = (
            '<rss xmlns:provider="https://trends.google.com/trends/trendingsearches/daily">'
            '<channel><item><title>query</title>'
            '<provider:approx_traffic>2K+</provider:approx_traffic>'
            '</item></channel></rss>'
        ).encode()
        self.assertEqual(parse_trends_feed(xml)[0].traffic_min, 2000)

    def test_unknown_fields_are_not_fabricated(self):
        result = parse_trends_feed(feed("<item><title>Запрос</title></item>"))[0]
        self.assertIsNone(result.traffic_min)
        self.assertEqual(result.traffic_label, "")
        self.assertIsNone(result.published_at)

    def test_invalid_or_unzoned_dates_are_unknown(self):
        for value in ["invalid", "Wed, 21 Oct 2026 15:00:00"]:
            with self.subTest(value=value):
                result = parse_trends_feed(feed(
                    f"<item><title>Запрос</title><pubDate>{value}</pubDate></item>"
                ))
                self.assertIsNone(result[0].published_at)

    def test_deduplicates_queries_and_skips_missing_title(self):
        result = parse_trends_feed(feed(
            "<item><title>  Запрос   один </title></item>"
            "<item><title>запрос один</title></item>"
            "<item><title> </title></item><item/>"
            "<item><title>Другой</title></item>"
        ))
        self.assertEqual([trend.query for trend in result], ["Запрос один", "Другой"])

    def test_non_rss_and_invalid_xml_raise_typed_error(self):
        for xml in [
            b"", b"<rss>", b"<html><body>Blocked</body></html>", b"<rss/>",
            b'<?xml version="1.0" encoding="unknown-encoding"?><rss><channel/></rss>',
        ]:
            with self.subTest(xml=xml), self.assertRaises(TrendSourceError):
                parse_trends_feed(xml)

    def test_rejects_xml_entities_and_oversized_feed(self):
        entity_feed = (
            b'<!DOCTYPE rss [<!ENTITY test "secret">]>'
            b"<rss><channel><item><title>&test;</title></item></channel></rss>"
        )
        for xml in [entity_feed, b"x" * (MAX_FEED_BYTES + 1)]:
            with self.subTest(length=len(xml)), self.assertRaises(TrendSourceError):
                parse_trends_feed(xml)


class FetchTrendsTests(unittest.TestCase):
    def response(self, content: bytes = b"", status: int = 200):
        response = MagicMock()
        response.status_code = status
        response.iter_content.return_value = [content]
        response.__enter__.return_value = response
        return response

    @patch("search_trends.requests.get")
    def test_fetches_only_kz_and_returns_aware_snapshot(self, get):
        response = self.response(feed("<item><title>Запрос</title></item>"))
        get.return_value = response
        snapshot = fetch_search_trends()
        self.assertEqual(snapshot.trends[0].query, "Запрос")
        self.assertEqual(snapshot.source_url, RSS_URL)
        self.assertEqual(snapshot.fetched_at.utcoffset().total_seconds(), 0)
        self.assertEqual(get.call_args.args, (RSS_URL,))
        self.assertEqual(get.call_args.kwargs["timeout"], REQUEST_TIMEOUT)
        self.assertTrue(get.call_args.kwargs["stream"])
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
        response.__exit__.assert_called_once()

    @patch("search_trends.requests.get")
    def test_http_errors_and_redirects_do_not_become_empty_success(self, get):
        for status in [403, 429, 500, 302]:
            get.return_value = self.response(status=status)
            with self.subTest(status=status), self.assertRaisesRegex(
                TrendSourceError, f"HTTP {status}"
            ):
                fetch_search_trends()

    @patch("search_trends.requests.get")
    def test_timeout_and_connection_error_are_typed(self, get):
        for error in [requests.Timeout(), requests.ConnectionError()]:
            get.side_effect = error
            with self.subTest(error=type(error)), self.assertRaises(TrendSourceError):
                fetch_search_trends()

    @patch("search_trends.requests.get")
    def test_streaming_timeout_is_typed_and_closes_response(self, get):
        response = self.response()
        response.iter_content.side_effect = requests.Timeout()
        get.return_value = response
        with self.assertRaises(TrendSourceError):
            fetch_search_trends()
        response.__exit__.assert_called_once()

    @patch("search_trends.requests.get")
    def test_bounded_body_and_invalid_server_response(self, get):
        for content in [b"x" * (MAX_FEED_BYTES + 1), b"<html>error</html>"]:
            get.return_value = self.response(content)
            with self.subTest(length=len(content)), self.assertRaises(TrendSourceError):
                fetch_search_trends()

    @patch("search_trends.requests.get")
    def test_feed_can_span_multiple_streaming_chunks(self, get):
        content = feed("<item><title>Запрос</title></item>")
        response = self.response()
        response.iter_content.return_value = [content[:15], b"", content[15:]]
        get.return_value = response
        self.assertEqual(fetch_search_trends().trends[0].query, "Запрос")


if __name__ == "__main__":
    unittest.main()
