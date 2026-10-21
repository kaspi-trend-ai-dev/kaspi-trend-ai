"""Regression checks for the existing CSV workflow."""

from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CSV_APP = """
import streamlit as st
from csv_analysis import render_csv_analysis
render_csv_analysis()
st.caption("CSV block finished")
"""


class CsvAnalysisTests(unittest.TestCase):
    def run_csv(self, csv=None):
        uploaded = None if csv is None else BytesIO(csv.encode("utf-8"))
        with patch("streamlit.file_uploader", return_value=uploaded):
            app = AppTest.from_string(CSV_APP).run(timeout=30)
        self.assertFalse(app.exception, list(app.exception))
        self.assertIn("CSV block finished", [item.value for item in app.caption])
        return app

    def test_no_file_shows_upload_guidance(self):
        app = self.run_csv()
        self.assertFalse(app.error)
        self.assertFalse(app.metric)
        self.assertIn("Загрузите данные", app.markdown[-1].value)

    def test_original_growth_seasonality_charts_and_export(self):
        app = self.run_csv(
            "date,category,value\n"
            "2024-01-01,Heaters,10\n2024-02-01,Heaters,20\n"
            "2025-01-01,Heaters,30\n2025-02-01,Heaters,60\n"
        )
        self.assertFalse(app.error)
        self.assertEqual(app.success[0].value, "Загружено 4 наблюдений")
        self.assertEqual(app.metric[0].value, "+100.0%")
        self.assertIn("№2", app.success[1].value)
        self.assertEqual(len(app.get("vega_lite_chart")), 2)
        self.assertEqual(len(app.get("download_button")), 1)

    def test_missing_columns_does_not_stop_other_sections(self):
        app = self.run_csv("wrong,value\nx,1\n")
        self.assertEqual(app.error[0].value, "Нужны столбцы: date, category, value")

    def test_timezone_boundary_preserves_original_calendar_months(self):
        with patch("streamlit.bar_chart") as bar_chart:
            app = self.run_csv(
                "date,category,value\n"
                "2025-01-01T00:00:00+05:00,Heaters,10\n"
                "2025-02-01T00:00:00+05:00,Heaters,20\n"
            )
        self.assertFalse(app.error)
        self.assertEqual(app.metric[0].value, "+100.0%")
        seasonal = bar_chart.call_args.args[0]
        self.assertEqual(seasonal.index.tolist(), [1, 2])
        self.assertEqual(seasonal.tolist(), [10.0, 20.0])

    def test_mixed_offsets_and_naive_dates_keep_local_calendar_dates(self):
        with patch("streamlit.line_chart") as line_chart:
            app = self.run_csv(
                "date,category,value\n"
                "2025-01-01T00:00:00+05:00,Heaters,10\n"
                "2025-02-01,Heaters,20\n"
                "2025-03-01T00:00:00+06:00,Heaters,30\n"
            )
        self.assertFalse(app.error)
        self.assertEqual(app.success[0].value, "Загружено 3 наблюдений")
        dates = line_chart.call_args.args[0].index
        self.assertIsNone(dates.tz)
        self.assertEqual(dates.month.tolist(), [1, 2, 3])
        self.assertEqual(dates.day.tolist(), [1, 1, 1])

    def test_invalid_rows_and_empty_categories_are_rejected(self):
        app = self.run_csv(
            "date,category,value\ninvalid,Heaters,wrong\n"
            "2025-01-01, ,1\n2025-02-01,Heaters,inf\n"
        )
        self.assertEqual(app.warning[0].value, "Нет корректных данных.")
        self.assertFalse(app.metric)

    def test_valid_rows_survive_mixed_invalid_input(self):
        app = self.run_csv(
            "date,category,value\n2025-01-01,Heaters,10\n"
            "invalid,Heaters,30\n2025-02-01,Heaters,20\n"
            "2025-03-01,,12\n2025-04-01,Heaters,-inf\n"
        )
        self.assertEqual(app.success[0].value, "Загружено 2 наблюдений")
        self.assertEqual(app.metric[0].value, "+100.0%")
        self.assertIn("Пропущено некорректных строк: 3.", [c.value for c in app.caption])

    def test_zero_previous_month_has_no_infinite_growth(self):
        app = self.run_csv(
            "date,category,value\n2025-01-01,Heaters,0\n2025-02-01,Heaters,20\n"
        )
        self.assertFalse(app.metric)
        self.assertEqual(app.warning[0].value, "Недостаточно данных для расчёта роста.")

    def test_empty_file_is_reported(self):
        app = self.run_csv("")
        self.assertIn("CSV-файл пуст", app.error[0].value)

    def test_malformed_csv_is_reported(self):
        app = self.run_csv('date,category,value\n2025-01-01,"Heaters,10\n')
        self.assertIn("Не удалось прочитать CSV", app.error[0].value)


if __name__ == "__main__":
    unittest.main()
