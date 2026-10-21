import unittest
import pandas as pd
from opportunity_ranking import analyze

class ReviewEstimatorTests(unittest.TestCase):
    def make_row(self, **extra):
        row = {"Товар": "TV", "Категория": "TV", "Цена": 10000,
               "Себестоимость": 5000, "Комиссия %": 20,
               "Доставка": 500, "Продавцов": 3}
        row.update(extra)
        return pd.DataFrame([row])

    def test_35_new_reviews_estimates_350_sales(self):
        result = analyze(self.make_row(**{"Отзывы 30д": 35}), 10)
        row = result.iloc[0]
        self.assertEqual(row["Прогноз продаж 30д"], 350)
        self.assertEqual(row["Прогноз оборота 30д"], 3500000)
        self.assertEqual(row["Прогноз прибыли 30д"], 875000)

    def test_total_reviews_not_used_as_new_reviews(self):
        result = analyze(self.make_row(**{"Отзывы": 500}), 10)
        self.assertTrue(pd.isna(result.iloc[0]["Прогноз продаж 30д"]))

    def test_multiplier_adjustable(self):
        result = analyze(self.make_row(**{"Отзывы 30д": 4}), 5)
        self.assertEqual(result.iloc[0]["Прогноз продаж 30д"], 20)

    def test_invalid_multiplier_rejected(self):
        with self.assertRaises(ValueError):
            analyze(self.make_row(), 0)

if __name__ == "__main__":
    unittest.main()
