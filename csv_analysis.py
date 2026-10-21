"""Analysis of user-uploaded CSV history, independent of live search trends."""

import numpy as np
import pandas as pd
import streamlit as st


def _local_calendar_date(value):
    """Keep the source's calendar day/month when removing timezone metadata."""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    return parsed.tz_localize(None)


def render_csv_analysis() -> None:
    """Render the original CSV workflow without stopping the rest of the app."""
    file = st.file_uploader(
        "Загрузите CSV с историей интереса к товарам",
        type=["csv"],
    )

    st.markdown("### Формат данных")
    st.code(
        "date,category,value\n2025-01-01,Обогреватели,42"
        "\n2025-02-01,Обогреватели,35"
    )
    st.caption(
        "Значения и их единицы определяются вашим CSV. "
        "Загрузка файла сама по себе не подтверждает, что это продажи Kaspi."
    )

    if file is None:
        st.write(
            "Загрузите данные, чтобы увидеть динамику, "
            "сезонность и изменение интереса."
        )
        return

    try:
        df = pd.read_csv(file)
        required = {"date", "category", "value"}
        if not required.issubset(df.columns):
            st.error("Нужны столбцы: date, category, value")
            return

        original_count = len(df)
        # Parse independently so mixed offsets/formats remain valid. Converting
        # to UTC first would move local Jan 1 observations into December.
        df["date"] = df["date"].map(_local_calendar_date)
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df["value"] = df["value"].replace([np.inf, -np.inf], np.nan)
        df["category"] = df["category"].astype("string").str.strip()
        df["category"] = df["category"].replace("", pd.NA)
        df = df.dropna(subset=["date", "category", "value"])
        df = df.sort_values("date")

        if df.empty:
            st.warning("Нет корректных данных.")
            return

        st.success(f"Загружено {len(df)} наблюдений")
        if len(df) != original_count:
            st.caption(f"Пропущено некорректных строк: {original_count - len(df)}.")

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
            growth = (monthly.iloc[-1] / monthly.iloc[-2] - 1) * 100
            st.metric("Изменение за месяц", f"{growth:+.1f}%")
        else:
            st.warning("Недостаточно данных для расчёта роста.")

        if data["date"].dt.year.nunique() >= 2:
            peak = seasonal.idxmax()
            st.success(
                "Исторически наиболее высокий средний "
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
            mime="text/csv",
        )
    except pd.errors.EmptyDataError:
        st.error("CSV-файл пуст. Нужны столбцы: date, category, value")
    except (pd.errors.ParserError, UnicodeError):
        st.error("Не удалось прочитать CSV. Проверьте формат файла и кодировку UTF-8.")
    except Exception as exc:
        st.error(f"Ошибка обработки: {exc}")
