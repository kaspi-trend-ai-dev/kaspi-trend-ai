"""UI and filtering checks using synthetic fixtures; these never call Google."""

import csv
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from search_trends import SearchTrend, TrendSnapshot, TrendSourceError
import trends_ui


NOW = datetime(2026, 10, 22, 10, tzinfo=timezone.utc)


def synthetic_trends(now=NOW):
    """Explicitly fictional queries for deterministic tests, not a live snapshot."""
    return (
        SearchTrend("Тестовый телефон", "10K+", 10_000, now - timedelta(hours=2), "https://trends.google.com/trends/explore?geo=KZ&q=test-phone"),
        SearchTrend("Тестовый ноутбук", "2K+", 2_000, now - timedelta(hours=30), "https://trends.google.com/trends/explore?geo=KZ&q=test-laptop"),
        SearchTrend("Тест без оценки", "", None, now - timedelta(hours=1), "https://trends.google.com/trends/explore?geo=KZ&q=test-unknown"),
        SearchTrend("Тест без даты", "500+", 500, None, "https://trends.google.com/trends/explore?geo=KZ&q=test-undated"),
    )


class TrendFilteringTests(unittest.TestCase):
    def test_literal_case_insensitive_query_and_minimum_volume(self):
        result = trends_ui.filter_trends(
            synthetic_trends(), query="  ТЕЛЕФОН ", min_traffic=5_000,
            include_unknown=False,
        )
        self.assertEqual([trend.query for trend in result], ["Тестовый телефон"])
        self.assertEqual(trends_ui.filter_trends(synthetic_trends(), query=".*"), [])

    def test_unknown_volume_is_optional_and_never_treated_as_zero(self):
        included = trends_ui.filter_trends(synthetic_trends(), min_traffic=5_000)
        self.assertEqual([t.query for t in included], ["Тестовый телефон", "Тест без оценки"])
        excluded = trends_ui.filter_trends(
            synthetic_trends(), min_traffic=5_000, include_unknown=False,
        )
        self.assertEqual([t.query for t in excluded], ["Тестовый телефон"])

    def test_period_filters_publication_and_excludes_missing_dates(self):
        result = trends_ui.filter_trends(synthetic_trends(), hours=24, now=NOW)
        self.assertEqual([t.query for t in result], ["Тестовый телефон", "Тест без оценки"])

    def test_sort_by_publication_and_alphabet(self):
        result = trends_ui.filter_trends(synthetic_trends(), sort="По дате публикации")
        self.assertEqual(result[0].query, "Тест без оценки")
        self.assertEqual(result[-1].query, "Тест без даты")
        alphabetical = trends_ui.filter_trends(synthetic_trends(), sort="По алфавиту")
        self.assertEqual(
            [t.query for t in alphabetical],
            sorted([t.query for t in synthetic_trends()], key=str.casefold),
        )

    def test_csv_preserves_unknowns_region_and_meaning_and_escapes_formulas(self):
        rows = list(synthetic_trends())
        rows.append(SearchTrend("=TEST_FORMULA()", "", None, None, "https://trends.google.com/"))
        exported = trends_ui.export_trends(rows)
        self.assertTrue(exported.startswith(b"\xef\xbb\xbf"))
        parsed = list(csv.DictReader(StringIO(exported.decode("utf-8-sig"))))
        self.assertEqual(len(parsed), 5)
        self.assertEqual(parsed[2]["Оценка поискового объёма"], "Нет данных")
        self.assertEqual(parsed[3]["Публикация (Алматы)"], "Нет данных")
        self.assertEqual(parsed[4]["Запрос"], "'=TEST_FORMULA()")
        self.assertTrue(all(row["Регион"] == "KZ" for row in parsed))
        self.assertTrue(all("не продажи Kaspi" in row["Тип данных"] for row in parsed))
        self.assertEqual(parsed[0]["Публикация (Алматы)"], "22.10.2026 13:00")


class TrendsAppTests(unittest.TestCase):
    def setUp(self):
        trends_ui.load_search_trends.clear()
        # Fixture times follow the test clock so the UI's relative date filter is stable.
        now = datetime.now(timezone.utc)
        self.snapshot = TrendSnapshot(synthetic_trends(now), now)
        self.fetch_patch = patch("trends_ui.fetch_search_trends", return_value=self.snapshot)
        self.fetch = self.fetch_patch.start()

    def tearDown(self):
        self.fetch_patch.stop()
        trends_ui.load_search_trends.clear()

    def run_app(self, csv_text=None):
        uploaded = None if csv_text is None else BytesIO(csv_text.encode("utf-8"))
        with patch("streamlit.file_uploader", return_value=uploaded):
            app = AppTest.from_file(str(REPO / "app.py")).run(timeout=30)
        self.assertFalse(app.exception, list(app.exception))
        return app

    def assert_no_exception(self, app):
        self.assertFalse(app.exception, list(app.exception))

    def test_successful_source_renders_table_source_and_separation(self):
        app = self.run_app()
        self.assertEqual(app.title[0].value, "📈 Kaspi Trend AI")
        self.assertEqual(len(app.dataframe[0].value), 4)
        self.assertIn("Это не продажи, заказы или поисковая статистика Kaspi", app.info[0].value)
        self.assertTrue(any("Регион: KZ" in c.value for c in app.caption))
        self.assertIn("Google Trends", app.markdown[0].value)
        self.assertFalse(app.error)
        self.assertEqual(self.fetch.call_count, 1)
        self.assertFalse(app.get("download_button")[0].proto.disabled)

    def test_filter_widgets_change_results_without_refetching(self):
        app = self.run_app()
        app.text_input(key="trend_query").set_value("ТЕЛЕФОН").run()
        self.assert_no_exception(app)
        self.assertEqual(app.dataframe[0].value["Запрос"].tolist(), ["Тестовый телефон"])
        app.text_input(key="trend_query").set_value("")
        app.number_input(key="trend_min_traffic").set_value(5_000)
        app.checkbox(key="trend_include_unknown").uncheck().run()
        self.assert_no_exception(app)
        self.assertEqual(app.dataframe[0].value["Запрос"].tolist(), ["Тестовый телефон"])
        self.assertEqual(self.fetch.call_count, 1)

    def test_publication_widget_and_unknown_fields(self):
        app = self.run_app()
        table = app.dataframe[0].value.set_index("Запрос")
        self.assertEqual(table.loc["Тест без оценки", "Оценка поискового объёма"], "Нет данных")
        self.assertEqual(table.loc["Тест без даты", "Публикация (Алматы)"], "Нет данных")
        app.selectbox(key="trend_period").select("24 часа").run()
        self.assert_no_exception(app)
        self.assertEqual(app.dataframe[0].value["Запрос"].tolist(), ["Тестовый телефон", "Тест без оценки"])

    def test_no_matching_rows_disables_export_and_explains_filters(self):
        app = self.run_app()
        app.text_input(key="trend_query").set_value("заведомо отсутствующий запрос").run()
        self.assert_no_exception(app)
        self.assertTrue(app.dataframe[0].value.empty)
        self.assertTrue(app.get("download_button")[0].proto.disabled)
        self.assertTrue(any("Нет запросов по выбранным фильтрам" in i.value for i in app.info))

    def test_unavailable_source_keeps_csv_analysis_usable(self):
        self.fetch.side_effect = TrendSourceError("Тест: источник недоступен")
        app = self.run_app(
            "date,category,value\n2024-01-01,Heaters,10\n2024-02-01,Heaters,20\n"
            "2025-01-01,Heaters,30\n2025-02-01,Heaters,60\n"
        )
        self.assertTrue(app.dataframe[0].value.empty)
        self.assertIn("Тест: источник недоступен", [w.value for w in app.warning])
        self.assertEqual(app.metric[0].value, "+100.0%")
        self.assertEqual(len(app.get("vega_lite_chart")), 2)
        self.assertEqual(app.success[0].value, "Загружено 4 наблюдений")

    def test_failure_after_success_retains_session_snapshot_with_warning(self):
        app = self.run_app()
        original_queries = app.dataframe[0].value["Запрос"].tolist()
        self.fetch.side_effect = TrendSourceError("Тест: повторная загрузка недоступна")
        trends_ui.load_search_trends.clear()
        app.run()
        self.assert_no_exception(app)
        self.assertEqual(app.dataframe[0].value["Запрос"].tolist(), original_queries)
        self.assertTrue(any("Данные могут быть устаревшими" in w.value for w in app.warning))
        self.assertEqual(self.fetch.call_count, 2)
        self.assertEqual(app.session_state[trends_ui.LAST_SUCCESS_KEY], self.snapshot)

    def test_valid_empty_source_is_distinct_from_failure(self):
        self.fetch.return_value = TrendSnapshot((), datetime.now(timezone.utc))
        app = self.run_app()
        self.assertTrue(app.dataframe[0].value.empty)
        self.assertFalse(app.warning)
        self.assertTrue(any("Источник вернул пустую ленту" in i.value for i in app.info))
        self.assertFalse(any("Данные пока не получены" in i.value for i in app.info))

    def test_manual_refresh_invalidates_cached_response(self):
        app = self.run_app()
        self.fetch.return_value = TrendSnapshot(
            (SearchTrend("Тестовый новый запрос", "100+", 100, None, "https://trends.google.com/"),),
            datetime.now(timezone.utc),
        )
        app.button(key="refresh_trends").click().run()
        self.assert_no_exception(app)
        self.assertEqual(self.fetch.call_count, 2)
        self.assertEqual(app.dataframe[0].value["Запрос"].tolist(), ["Тестовый новый запрос"])


if __name__ == "__main__":
    unittest.main()
