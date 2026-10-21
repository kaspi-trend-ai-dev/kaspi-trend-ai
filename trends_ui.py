"""Streamlit view for the Kazakhstan search feed, independent of CSV analysis."""

import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from search_trends import (
    CACHE_TTL_SECONDS,
    RSS_URL,
    SOURCE_NAME,
    SearchTrend,
    TrendSnapshot,
    TrendSourceError,
    fetch_search_trends,
)


ALMATY = ZoneInfo("Asia/Almaty")
LAST_SUCCESS_KEY = "search_trends_last_success"
PERIODS = {"Вся доступная лента": None, "24 часа": 24, "48 часов": 48, "7 дней": 168}
TABLE_COLUMNS = ["Запрос", "Оценка поискового объёма", "Публикация (Алматы)", "Источник"]


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False, max_entries=1)
def load_search_trends() -> tuple[TrendSnapshot | None, str | None]:
    # Cache failures too, so changing filters does not repeatedly hit an unavailable feed.
    try:
        return fetch_search_trends(), None
    except TrendSourceError as exc:
        return None, str(exc)


def filter_trends(
    trends: tuple[SearchTrend, ...],
    query: str = "",
    min_traffic: int = 0,
    include_unknown: bool = True,
    hours: int | None = None,
    sort: str = "По объёму",
    now: datetime | None = None,
) -> list[SearchTrend]:
    """Filter only published source fields; never infer sales or product categories."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=hours) if hours else None
    needle = query.strip().casefold()
    results = [
        trend for trend in trends
        if needle in trend.query.casefold()
        and (
            (trend.traffic_min is None and include_unknown)
            or (trend.traffic_min is not None and trend.traffic_min >= min_traffic)
        )
        and (cutoff is None or (trend.published_at is not None and trend.published_at >= cutoff))
    ]
    if sort == "По дате публикации":
        results.sort(key=lambda trend: trend.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    elif sort == "По алфавиту":
        results.sort(key=lambda trend: trend.query.casefold())
    else:
        results.sort(key=lambda trend: trend.traffic_min if trend.traffic_min is not None else -1, reverse=True)
    return results


def _display_rows(trends: list[SearchTrend]) -> list[dict]:
    return [
        dict(zip(TABLE_COLUMNS, [
            trend.query,
            trend.traffic_label or "Нет данных",
            trend.published_at.astimezone(ALMATY).strftime("%d.%m.%Y %H:%M") if trend.published_at else "Нет данных",
            trend.url,
        ]))
        for trend in trends
    ]


def export_trends(trends: list[SearchTrend]) -> bytes:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([*TABLE_COLUMNS, "Регион", "Тип данных"])
    for row in _display_rows(trends):
        # External query text may be opened in spreadsheet software.
        cells = [f"'{value}" if value.lstrip().startswith(("=", "+", "-", "@")) else value for value in row.values()]
        writer.writerow([*cells, "KZ", "Поисковый интерес Google; не продажи Kaspi"])
    return buffer.getvalue().encode("utf-8-sig")


@st.fragment(run_every=CACHE_TTL_SECONDS)
def render_search_trends() -> None:
    st.subheader("Что ищут в Казахстане")
    st.caption(
        "Google Trends · Казахстан (KZ). Автоматическая загрузка при открытии и каждые 15 минут, "
        "пока страница открыта. Доступность и состав ленты зависят от Google."
    )
    refresh_col, source_col = st.columns([1, 3])
    if refresh_col.button("Обновить тренды", key="refresh_trends"):
        load_search_trends.clear()
    source_col.markdown(f"[Открыть Google Trends для Казахстана](https://trends.google.com/trending?geo=KZ) · [RSS-источник]({RSS_URL})")

    with st.spinner("Получаем поисковые тренды Казахстана…"):
        snapshot, error = load_search_trends()
    if snapshot is not None:
        st.session_state[LAST_SUCCESS_KEY] = snapshot
    else:
        snapshot = st.session_state.get(LAST_SUCCESS_KEY)
        st.warning(error or "Источник поисковых трендов временно недоступен.")
        if snapshot is not None:
            st.warning("Показан последний успешно полученный результат. Данные могут быть устаревшими.")
        else:
            st.info("Данные пока не получены. Повторите загрузку кнопкой «Обновить тренды». Анализ CSV доступен во второй вкладке.")

    trends = snapshot.trends if snapshot is not None else ()
    if snapshot is not None:
        st.caption(
            f"Последнее успешное получение: {snapshot.fetched_at.astimezone(ALMATY):%d.%m.%Y %H:%M} "
            f"(Алматы) · {SOURCE_NAME} RSS · Регион: KZ"
        )
        if not trends:
            st.info("Источник вернул пустую ленту для Казахстана. Попробуйте обновить её позже.")

    query_col, traffic_col, period_col = st.columns([2, 1, 1])
    query = query_col.text_input("Поиск по запросу", placeholder="Например, iPhone", key="trend_query")
    min_traffic = traffic_col.number_input("Минимальная оценка объёма", min_value=0, value=0, step=100, key="trend_min_traffic")
    period = period_col.selectbox("Дата публикации", list(PERIODS), key="trend_period")
    unknown_col, sort_col = st.columns([2, 1])
    include_unknown = unknown_col.checkbox("Показывать запросы без оценки объёма", value=True, key="trend_include_unknown")
    sort = sort_col.selectbox("Сортировка", ["По объёму", "По дате публикации", "По алфавиту"], key="trend_sort")
    filtered = filter_trends(trends, query, int(min_traffic), include_unknown, PERIODS[period], sort)

    st.caption(f"Показано {len(filtered)} из {len(trends)} запросов в доступной ленте.")
    if trends and not filtered:
        st.info("Нет запросов по выбранным фильтрам. Измените условия поиска.")
    st.dataframe(
        pd.DataFrame(_display_rows(filtered), columns=TABLE_COLUMNS),
        hide_index=True,
        column_config={"Источник": st.column_config.LinkColumn("Источник", display_text="Google Trends")},
    )
    st.caption(
        "Оценка объёма — приблизительный поисковый объём из RSS, а «+» обозначает нижнюю границу. "
        "Это не индекс 0–100 и не количество покупок. Период фильтрует дату публикации записи; "
        "он не задаёт период измерения объёма. Записи без даты доступны в режиме «Вся доступная лента»."
    )
    st.download_button(
        "Скачать поисковые тренды CSV",
        export_trends(filtered),
        file_name="google_search_trends_KZ.csv",
        mime="text/csv",
        disabled=not filtered,
        key="download_search_trends",
    )
