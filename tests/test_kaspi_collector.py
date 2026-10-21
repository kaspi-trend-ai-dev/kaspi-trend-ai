import unittest
from unittest.mock import patch
from kaspi_collector import extract_metadata, collect

URL = "https://kaspi.kz/shop/p/dishop-43ns77-109-sm-chernyi-161213427/?m=14956007&ms=true"

class KaspiCollectorTests(unittest.TestCase):
    def test_product_json_ld(self):
        page = """<html><script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Product",
        "name":"DISHOP 43NS77","offers":{"@type":"Offer","price":"129990","priceCurrency":"KZT"},
        "aggregateRating":{"ratingValue":"4.8","reviewCount":"25"}}
        </script></html>"""
        record = extract_metadata(page, URL)
        self.assertEqual(record["title"], "DISHOP 43NS77")
        self.assertEqual(record["price"], 129990.0)
        self.assertEqual(record["currency"], "KZT")
        self.assertEqual(record["review_count"], "25")

    def test_open_graph_fallback(self):
        record = extract_metadata('<meta property="og:title" content="DISHOP TV">', URL)
        self.assertEqual(record["title"], "DISHOP TV")
        self.assertIsNone(record["price"])

    def test_rejects_external_domains(self):
        with self.assertRaises(ValueError):
            collect("https://kaspi.kz.evil.example/shop/p/x")

if __name__ == "__main__":
    unittest.main()
