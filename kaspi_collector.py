"""Conservative public Kaspi product-page snapshot collector.

Only fetch URLs supplied by the operator. Does not crawl categories, bypass
access controls, or infer sales. Respect Kaspi terms and robots policy before use.
Run: python kaspi_collector.py 'https://kaspi.kz/shop/p/...'
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
from html.parser import HTMLParser
import json
import re
import sqlite3
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class ProductMetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.json_ld = []
        self._script = False
        self._script_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = attrs.get("property") or attrs.get("name")
            if key and attrs.get("content"):
                self.meta[key.lower()] = html.unescape(attrs["content"])
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self._script = True
            self._script_parts = []

    def handle_data(self, data):
        if self._script:
            self._script_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._script:
            try:
                self.json_ld.append(json.loads("".join(self._script_parts)))
            except json.JSONDecodeError:
                pass
            self._script = False


def _products(node):
    if isinstance(node, list):
        for child in node:
            yield from _products(child)
    elif isinstance(node, dict):
        types = node.get("@type", [])
        if isinstance(types, str):
            types = [types]
        if "Product" in types:
            yield node
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                yield from _products(node[key])


def extract_metadata(page: str, url: str) -> dict:
    parser = ProductMetadataParser()
    parser.feed(page)
    product = next((p for block in parser.json_ld for p in _products(block)), {})
    offers = product.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}
    rating = product.get("aggregateRating", {})
    if not isinstance(rating, dict):
        rating = {}
    price = offers.get("price")
    if price is not None:
        try:
            price = float(str(price).replace(" ", "").replace(",", "."))
        except ValueError:
            price = None
    return {
        "url": url,
        "title": product.get("name") or parser.meta.get("og:title"),
        "price": price,
        "currency": offers.get("priceCurrency"),
        "availability": offers.get("availability"),
        "rating": rating.get("ratingValue"),
        "review_count": rating.get("reviewCount"),
        "description": product.get("description") or parser.meta.get("og:description"),
        "source": "public_html_metadata",
    }


def collect(url: str, timeout: int = 15) -> dict:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"kaspi.kz", "www.kaspi.kz"}:
        raise ValueError("Only HTTPS kaspi.kz URLs are allowed")
    if not parsed.path.startswith("/shop/p/"):
        raise ValueError("Expected a Kaspi product URL under /shop/p/")
    request = Request(url, headers={"User-Agent": "KaspiTrendAIResearch/0.1 (single-page metadata)"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Unexpected HTTP status: {response.status}")
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("Page too large")
        charset = response.headers.get_content_charset() or "utf-8"
    record = extract_metadata(body.decode(charset, errors="replace"), url)
    if not record["title"]:
        raise RuntimeError("No product metadata found; page may require JavaScript or restrict access")
    return record


def save_snapshot(record: dict, db_path: str = "kaspi_snapshots.sqlite3") -> None:
    with sqlite3.connect(db_path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_at TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            price REAL,
            currency TEXT,
            availability TEXT,
            rating TEXT,
            review_count TEXT,
            description TEXT,
            source TEXT NOT NULL
        )""")
        db.execute("""INSERT INTO snapshots (
            captured_at, url, title, price, currency, availability,
            rating, review_count, description, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
            dt.datetime.now(dt.timezone.utc).isoformat(),
            record["url"], record["title"], record["price"], record["currency"],
            record["availability"], record["rating"], record["review_count"],
            record["description"], record["source"],
        ))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("url", help="Public Kaspi product page")
    cli.add_argument("--database", default="kaspi_snapshots.sqlite3")
    args = cli.parse_args()
    result = collect(args.url)
    save_snapshot(result, args.database)
    print(json.dumps(result, ensure_ascii=False, indent=2))
