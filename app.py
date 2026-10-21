import streamlit as st

from csv_analysis import render_csv_analysis
from trends_ui import render_search_trends


st.set_page_config(page_title="Kaspi Trend AI", page_icon="📈", layout="wide")

st.title("📈 Kaspi Trend AI")
st.caption("Поисковые тренды Казахстана и анализ ваших CSV")
st.info(
    "Google Trends показывает поисковый интерес в Google по Казахстану. "
    "Это не продажи, заказы или поисковая статистика Kaspi. "
    "Прямое подключение к статистике Kaspi не настроено."
)

trends_tab, csv_tab = st.tabs(["Поисковые тренды · Казахстан", "Анализ CSV"])
with trends_tab:
    render_search_trends()
with csv_tab:
    render_csv_analysis()

st.divider()
st.caption("Kaspi Trend AI · Поисковый интерес и пользовательские данные · Данные о продажах не подключены")
