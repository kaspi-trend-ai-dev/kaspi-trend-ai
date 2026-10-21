import unittest
from product_opportunities import parse_product, validate_product_url

URL = "https://kaspi.kz/shop/p/dishop-43ns77-109-sm-chernyi-161213427/"

class ProductOpportunitiesTests(unittest.TestCase):
    def test_public_meta_price(self):
        page = ('<meta property="og:title" content="DISHOP 43NS77">'
                '<meta property="product:price:amount" content="129990">'
                '<meta property="product:price:currency" content="KZT">')
        data = parse_product(page, URL)
        self.assertEqual(data["Цена, ₸"], 129990.0)
        self.assertEqual(data["ID"], "161213427")
        self.assertEqual(data["Валюта"], "KZT")

    def test_no_fake_price(self):
        data = parse_product('<meta property="og:title" content="TV">', URL)
        self.assertIsNone(data["Цена, ₸"])
        self.assertIsNone(data["Отзывы"])

    def test_reject_other_domains(self):
        with self.assertRaises(ValueError):
            validate_product_url("https://kaspi.kz.evil.test/shop/p/123")

if __name__ == "__main__":
    unittest.main()
