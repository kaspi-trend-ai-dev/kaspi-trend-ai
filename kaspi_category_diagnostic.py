"""Diagnose whether Kaspi exposes publicly crawlable category product links.

Bounded to two category pages, respecting robots.txt. Never bypass access controls.
Only aggregates are logged, no page bodies, cookies or private endpoints.
"""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import requests

BASE = "https://kaspi.kz"
CATEGORIES = [
    "https://kaspi.kz/shop/c/tvs/all/",
    "https://kaspi.kz/shop/c/smartphones/",
]
UA = "KaspiTrendAIResearch/0.3 (public catalog discovery)"

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.add(href)

def main():
    try:
        response = requests.get(BASE + "/robots.txt", timeout=(5, 12), headers={"User-Agent": UA})
        response.raise_for_status()
        robots = RobotFileParser()
        robots.parse(response.text.splitlines())
        print("ROBOTS_STATUS: available")
    except requests.RequestException as exc:
        print("ROBOTS_STATUS: unavailable", type(exc).__name__)
        return
    for url in CATEGORIES:
        if not robots.can_fetch(UA, url):
            print("CATEGORY:", urlparse(url).path, "ROBOTS_DISALLOW")
            continue
        try:
            response = requests.get(url, timeout=(5, 12), headers={"User-Agent": UA}, allow_redirects=False)
            print("CATEGORY:", urlparse(url).path, "STATUS:", response.status_code)
            if response.status_code != 200 or "html" not in response.headers.get("Content-Type", "").lower():
                continue
            if len(response.content) > 2_000_000:
                print("OVERSIZE")
                continue
            parser = Links()
            parser.feed(response.text)
            products = {
                urljoin(url, link).split("?")[0]
                for link in parser.links
                if urlparse(urljoin(url, link)).hostname == "kaspi.kz"
                and urlparse(urljoin(url, link)).path.startswith("/shop/p/")
            }
            print("PRODUCT_LINK_COUNT:", len(products))
            print("HAS_PRODUCT_LINKS:", bool(products))
            print("HAS_PRICE_TEXT:", "Цена" in response.text)
            print("HAS_REVIEWS_TEXT:", "отзыв" in response.text.lower())
            print("HAS_JSON_LD:", "application/ld+json" in response.text.lower())
            print("HTML_BYTES:", len(response.content))
        except (requests.RequestException, ValueError) as exc:
            print("CATEGORY_ERROR:", type(exc).__name__)

if __name__ == "__main__":
    main()
