
import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(
    page_title="Kaspi Trend AI",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Kaspi Trend AI")
st.caption("Анализ сезонности и перспективных товарных категорий")

st.info(
    "Сервис анализирует загруженные данные. "
    "Прямое подключение к статистике Kaspi пока не настроено."
)

file = st.file_uploader(
    "Загрузите CSV с историей интереса к товарам",
    type=["csv"]
)

st.markdown("### Формат данных")
st.code("date,category,value\n2025-01-01,Обогреватели,42\n2025-02-01,Обогреватели,35")

if file is not None:
    try:
        df = pd.read_csv(file)
        required = {"date", "category", "value"}

        if not required.issubset(df.columns):
            st.error("Нужны столбцы: date, category, value")
            st.stop()

        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["date", "category", "value"])
        df = df.sort_values("date")

        if df.empty:
            st.warning("Нет корректных данных.")
            st.stop()

        st.success(f"Загружено {len(df)} наблюдений")

        categories = sorted(df["category"].unique())
        selected = st.selectbox("Выберите категорию", categories)
        data = df[df["category"] == selected].copy()

        st.subheader("Динамика интереса")
        st.line_chart(data.set_index("date")["value"])

        st.subheader("Средний интерес по месяцам")
        data["month"] = data["date"].dt.month
        seasonal = data.groupby("month")["value"].mean()
        st.bar_chart(seasonal)

        st.subheader("Анализ динамики")
        monthly = (
            data.set_index("date")["value"]
            .resample("MS").mean().dropna()
        )

        if len(monthly) >= 2 and monthly.iloc[-2] != 0:
            growth = (
                monthly.iloc[-1] / monthly.iloc[-2] - 1
            ) * 100
            st.metric("Изменение за месяц", f"{growth:+.1f}%")
        else:
            st.warning("Недостаточно данных для расчёта роста.")

        if data["date"].dt.year.nunique() >= 2:
            peak = seasonal.idxmax()
            st.success(
                f"Исторически наиболее высокий средний "
                f"интерес наблюдался в месяце №{peak}."
            )
        else:
            st.info(
                "Для надёжного анализа сезонности "
                "желательно минимум 2–3 года данных."
            )

        st.download_button(
            "Скачать обработанные данные",
            data.to_csv(index=False).encode("utf-8-sig"),
            file_name="trend_analysis.csv",
            mime="text/csv"
        )

    except Exception as e:
        st.error(f"Ошибка обработки: {e}")
else:
    st.write(
        "Загрузите данные, чтобы увидеть динамику, "
        "сезонность и изменение интереса."
    )

st.divider()
st.caption("Kaspi Trend AI · MVP · Данные о продажах не подключены")
