import unittest
import pandas as pd
from opportunity_ranking import analyze

class RankingTests(unittest.TestCase):
    def test_real_margin_and_unknown_orders(self):
        df = pd.DataFrame([{
            "Товар": "TV", "Категория": "Электроника",
            "Цена": 129990, "Себестоимость": 77500,
            "Комиссия %": 20, "Доставка": 500, "Продавцов": 4,
        }])
        result = analyze(df)
        self.assertEqual(result.iloc[0]["Прибыль/шт"], 25992)
        self.assertFalse(bool(result.iloc[0]["Спрос подтверждён"]))
        self.assertTrue(pd.isna(result.iloc[0]["Прибыль 30д (если заказы известны)"]))

    def test_rejects_invalid_rows(self):
        with self.assertRaises(ValueError):
            analyze(pd.DataFrame([{
                "Товар": "Bad", "Категория": "X",
                "Цена": -1, "Себестоимость": 10,
                "Комиссия %": 20, "Доставка": 5, "Продавцов": 0,
            }]))

    def test_known_orders(self):
        df = pd.DataFrame([{
            "Товар": "A", "Категория": "X", "Цена": 1000,
            "Себестоимость": 500, "Комиссия %": 10,
            "Доставка": 100, "Продавцов": 2, "Заказы 30д": 10,
        }])
        result = analyze(df)
        self.assertEqual(result.iloc[0]["Прибыль 30д (если заказы известны)"], 3000)
        self.assertTrue(bool(result.iloc[0]["Спрос подтверждён"]))

if __name__ == "__main__":
    unittest.main()
