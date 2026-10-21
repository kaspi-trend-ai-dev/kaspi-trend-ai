import streamlit as st

from csv_analysis import render_csv_analysis
from trends_ui import render_search_trends
from product_opportunities import render_product_opportunities


st.set_page_config(page_title="Kaspi Trend AI", page_icon="📈", layout="wide")

st.title("📈 Kaspi Trend AI")
st.caption("Публичные карточки Kaspi, поисковые тренды и анализ CSV")
st.info(
    "Google Trends показывает поисковый интерес в Google по Казахстану. "
    "Это не продажи, заказы или поисковая статистика Kaspi. "
    "Прямое подключение к статистике Kaspi не настроено."
)

trends_tab, csv_tab, products_tab = st.tabs(["Поисковые тренды · Казахстан", "Анализ CSV", "Товары Kaspi"])
with trends_tab:
    render_search_trends()
with csv_tab:
    render_csv_analysis()
with products_tab:
    render_product_opportunities()

st.divider()
st.caption("Kaspi Trend AI · Поисковый интерес и пользовательские данные · Данные о продажах не подключены")
