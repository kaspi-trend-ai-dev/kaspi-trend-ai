"""Check public Kaspi product pages for *verifiable* review counts.

This diagnostic does not guess counts, call undocumented endpoints, or bypass robots.
"""
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse
from product_opportunities import SAMPLE_URL, parse_product
import requests

USER_AGENT = "KaspiTrendAIResearch/0.3 (public metadata diagnostic)"

def inspect(url=SAMPLE_URL, get=requests.get):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "kaspi.kz" or not parsed.path.startswith("/shop/p/"):
        raise ValueError("Only public Kaspi product URLs")
    robots_response = get("https://kaspi.kz/robots.txt", timeout=(5, 12), headers={"User-Agent": USER_AGENT})
    robots_response.raise_for_status()
    robots = RobotFileParser()
    robots.parse(robots_response.text.splitlines())
    if not robots.can_fetch(USER_AGENT, url):
        return {"status": "ROBOTS_DISALLOW"}
    response = get(url, timeout=(5, 12), headers={"User-Agent": USER_AGENT}, allow_redirects=False)
    if response.status_code != 200:
        return {"status": f"HTTP_{response.status_code}"}
    if "html" not in response.headers.get("Content-Type", "").lower() or len(response.content) > 2_000_000:
        return {"status": "UNSUPPORTED_RESPONSE"}
    product = parse_product(response.text, url)
    raw = product["Отзывы"]
    try:
        count = int(raw)
        if count < 0 or str(raw).strip() != str(count):
            count = None
    except (ValueError, TypeError):
        count = None
    return {
        "status": "OK",
        "product_id": product["ID"],
        "has_title": bool(product["Товар"]),
        "has_price": product["Цена, ₸"] is not None,
        "review_count": count,
        "has_rating": product["Рейтинг"] is not None,
        "html_bytes": len(response.content),
    }

if __name__ == "__main__":
    import json
    print(json.dumps(inspect(), ensure_ascii=False))
