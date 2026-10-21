"""Evidence-based product opportunity ranking from actual seller data.

No fabricated competitor sales: optional 30-day orders must be supplied by user.
"""
from __future__ import annotations
import pandas as pd
import streamlit as st

COLUMNS = ["Товар", "Категория", "Цена", "Себестоимость", "Комиссия %", "Доставка", "Продавцов", "Заказы 30д", "Отзывы"]
NUMERIC = ["Цена", "Себестоимость", "Комиссия %", "Доставка", "Продавцов", "Заказы 30д", "Отзывы"]


def analyze(df):
    missing = [c for c in COLUMNS[:7] if c not in df.columns]
    if missing:
        raise ValueError("Отсутствуют колонки: " + ", ".join(missing))
    if df.empty:
        raise ValueError("Файл не содержит товаров")
    if len(df) > 20000:
        raise ValueError("Не более 20 000 строк")
    result = df.copy()
    for name in NUMERIC:
        if name not in result:
            result[name] = float("nan")
        result[name] = pd.to_numeric(result[name], errors="coerce")
    result["Товар"] = result["Товар"].fillna("").astype(str).str.strip()
    result["Категория"] = result["Категория"].fillna("").astype(str).str.strip()
    valid = (
        result["Товар"].ne("") & result["Категория"].ne("")
        & result["Цена"].gt(0) & result["Себестоимость"].ge(0)
        & result["Комиссия %"].between(0, 100)
        & result["Доставка"].ge(0)
        & result["Продавцов"].ge(1)
    )
    result = result.loc[valid].copy()
    if result.empty:
        raise ValueError("Нет строк с корректными ценами, затратами и количеством продавцов")
    result["Прибыль/шт"] = (
        result["Цена"] * (1 - result["Комиссия %"] / 100)
        - result["Себестоимость"] - result["Доставка"]
    )
    result["Маржа %"] = (result["Прибыль/шт"] / result["Цена"] * 100).round(1)
    # These are ranking signals, NOT a prediction of sales.
    result["Конкуренция"] = result["Продавцов"].map(
        lambda n: "Низкая" if n <= 5 else ("Средняя" if n <= 15 else "Высокая")
    )
    result["Спрос подтверждён"] = result["Заказы 30д"].ge(1)
    result["Прибыль 30д (если заказы известны)"] = (
        result["Прибыль/шт"] * result["Заказы 30д"].where(result["Заказы 30д"].ge(0))
    )
    result["Балл возможностей"] = (
        result["Маржа %"].clip(0, 50) / 50 * 60
        + (1 / result["Продавцов"].clip(lower=1).pow(0.5)) * 40
    ).round(1)
    return result.sort_values("Балл возможностей", ascending=False)


def render_opportunity_ranking():
    st.subheader("Поиск перспективных товаров")
    st.caption("Сравнение товаров по фактической экономике и конкуренции. Заказы и отзывы необязательны.")
    st.info(
        "Это аналитика предоставленных данных, а не автоматически измеренные продажи Kaspi. "
        "Балл отражает маржу и количество продавцов, а не доказанный спрос."
    )
    st.markdown(
        "**Формат CSV:** Товар, Категория, Цена, Себестоимость, Комиссия %, "
        "Доставка, Продавцов; дополнительно — Заказы 30д и Отзывы."
    )
    template = pd.DataFrame(columns=COLUMNS)
    st.download_button("Скачать шаблон CSV", template.to_csv(index=False).encode("utf-8-sig"), "product_opportunities_template.csv", "text/csv")
    uploaded = st.file_uploader("Загрузить таблицу товаров CSV", type=["csv"], key="opportunity_csv")
    if uploaded is None:
        st.caption("Таблица пуста до загрузки данных. Демонстрационные товары не подставляются.")
        return
    try:
        if uploaded.size > 4_000_000:
            raise ValueError("Максимальный размер CSV — 4 МБ")
        frame = pd.read_csv(uploaded, encoding="utf-8-sig")
        result = analyze(frame)
    except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
        st.error(f"Не удалось обработать файл: {exc}")
        return
    minimum = st.slider("Минимальная маржа, %", min_value=0, max_value=70, value=15)
    maximum = st.number_input("Максимум продавцов", min_value=1, max_value=100000, value=15)
    category = st.selectbox("Категория", ["Все"] + sorted(result["Категория"].unique().tolist()))
    filtered = result[result["Маржа %"].ge(minimum) & result["Продавцов"].le(maximum)]
    if category != "Все":
        filtered = filtered[filtered["Категория"].eq(category)]
    st.metric("Подходящих товаров", len(filtered))
    st.metric("С подтверждёнными заказами", int(filtered["Спрос подтверждён"].sum()))
    st.dataframe(filtered, use_container_width=True, hide_index=True)
    st.download_button("Скачать результаты", filtered.to_csv(index=False).encode("utf-8-sig"), "ranked_opportunities.csv", "text/csv")
    st.caption("Без фактических заказов рейтинг нельзя интерпретировать как топ продаж.")
