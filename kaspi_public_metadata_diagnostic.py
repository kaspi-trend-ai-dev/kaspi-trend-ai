"""Inspect public HTML metadata for one operator-supplied Kaspi product URL.

No internal APIs, browser automation, or bypasses. Prints only field presence,
not page HTML, tokens, cookies or personal data.
"""
from __future__ import annotations

import os
from html.parser import HTMLParser
from urllib.request import Request, urlopen

from kaspi_collector import extract_metadata

PRODUCT_URL = os.environ.get(
    "PRODUCT_URL",
    "https://kaspi.kz/shop/p/dishop-43ns77-109-sm-chernyi-161213427/?m=14956007&ms=true",
)


class PublicMetadataInventory(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta_keys = set()
        self.itemprops = set()
        self.ld_json_blocks = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = attrs.get("property") or attrs.get("name")
            if key:
                self.meta_keys.add(key.lower())
        if attrs.get("itemprop"):
            self.itemprops.add(attrs["itemprop"].lower())
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.ld_json_blocks += 1


def main():
    request = Request(
        PRODUCT_URL,
        headers={"User-Agent": "KaspiTrendAIResearch/0.1 (single-page metadata)"},
    )
    with urlopen(request, timeout=12) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Page too large")
        page = raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    inventory = PublicMetadataInventory()
    inventory.feed(page)
    record = extract_metadata(page, PRODUCT_URL)
    print("PUBLIC_METADATA_INSPECTION")
    print("Title present:", bool(record["title"]))
    for key in ("price", "currency", "availability", "rating", "review_count"):
        print(f"{key} present:", record[key] is not None)
    print("JSON-LD script count:", inventory.ld_json_blocks)
    for key in ("product:price:amount", "product:price:currency", "og:price:amount", "og:price:currency"):
        print(f"meta {key} present:", key in inventory.meta_keys)
    for key in ("price", "pricecurrency", "availability", "ratingvalue", "reviewcount"):
        print(f"itemprop {key} present:", key in inventory.itemprops)


if __name__ == "__main__":
    main()
