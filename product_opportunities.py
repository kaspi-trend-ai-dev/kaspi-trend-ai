"""Public Kaspi product metadata and a cautious opportunity dashboard."""
from __future__ import annotations

import html
from html.parser import HTMLParser
import json
import re
from urllib.parse import urlparse
import requests
import streamlit as st
import pandas as pd

SAMPLE_URL = "https://kaspi.kz/shop/p/dishop-43ns77-109-sm-chernyi-161213427/"
MAX_URLS = 12


class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.jsonld = []
        self._capture = False
        self._parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            name = attrs.get("property") or attrs.get("name")
            if name and attrs.get("content"):
                self.meta[name.lower()] = html.unescape(attrs["content"])
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self._capture = True
            self._parts = []

    def handle_data(self, data):
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._capture:
            try:
                self.jsonld.append(json.loads("".join(self._parts)))
            except (ValueError, TypeError):
                pass
            self._capture = False


def products_in(node):
    if isinstance(node, list):
        for item in node:
            yield from products_in(item)
    if isinstance(node, dict):
        kinds = node.get("@type", [])
        if isinstance(kinds, str):
            kinds = [kinds]
        if "Product" in kinds:
            yield node
        for key in ("@graph", "mainEntity"):
            if key in node:
                yield from products_in(node[key])


def validate_product_url(url):
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.hostname not in ("kaspi.kz", "www.kaspi.kz"):
        raise ValueError("Требуется HTTPS-ссылка на kaspi.kz")
    if not parsed.path.startswith("/shop/p/"):
        raise ValueError("Нужна ссылка на карточку товара /shop/p/")
    return url.strip()


def parse_product(page, url):
    parser = MetaParser()
    parser.feed(page)
    product = next((p for block in parser.jsonld for p in products_in(block)), {})
    offer = product.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}
    if not isinstance(offer, dict):
        offer = {}
    rating = product.get("aggregateRating") or {}
    if not isinstance(rating, dict):
        rating = {}
    raw_price = offer.get("price") or parser.meta.get("product:price:amount")
    price = None
    if raw_price is not None:
        try:
            price = float(str(raw_price).replace(" ", "").replace(",", "."))
        except ValueError:
            pass
    match = re.search(r"-(\d+)/?$", urlparse(url).path)
    return {
        "ID": match.group(1) if match else "",
        "Товар": product.get("name") or parser.meta.get("og:title") or "",
        "Цена, ₸": price,
        "Валюта": offer.get("priceCurrency") or parser.meta.get("product:price:currency") or "",
        "Рейтинг": rating.get("ratingValue"),
        "Отзывы": rating.get("reviewCount"),
        "Ссылка": url,
    }


@st.cache_data(ttl=900, show_spinner=False)
def load_product(url):
    url = validate_product_url(url)
    response = requests.get(
        url, timeout=(6, 12), headers={"User-Agent": "KaspiTrendAIResearch/0.2 (public product metadata)"},
        allow_redirects=False,
    )
    response.raise_for_status()
    if 300 <= response.status_code < 400:
        raise ValueError("Перенаправление не поддерживается")
    if len(response.content) > 2_000_000:
        raise ValueError("Страница слишком большая")
    if "html" not in response.headers.get("Content-Type", "").lower():
        raise ValueError("Источник вернул не HTML")
    item = parse_product(response.text, url)
    if not item["Товар"]:
        raise ValueError("Не удалось прочитать карточку")
    return item


def render_product_opportunities():
    st.subheader("Товарная аналитика Kaspi — первая версия")
    st.caption("Реальные публичные карточки Kaspi, без вымышленных продаж. Данные загружаются при открытии и кешируются на 15 минут.")
    st.warning(
        "Kaspi не предоставляет здесь подтверждённые продажи конкурентов. "
        "Цена и карточка не позволяют достоверно рассчитать спрос, оборот или рейтинг продаваемости. "
        "Пока это мониторинг доступности товарных данных, а не полноценный SaleScout."
    )
    urls_text = st.text_area(
        "Ссылки на товары Kaspi (по одной в строке)",
        value=SAMPLE_URL,
        height=100,
        help="Проверяется только указанный список; автоматического обхода категорий пока нет.",
    )
    if st.button("Загрузить карточки", type="primary"):
        urls = list(dict.fromkeys(line.strip() for line in urls_text.splitlines() if line.strip()))
        if len(urls) > MAX_URLS:
            st.error(f"Максимум {MAX_URLS} ссылок за запрос.")
            return
        records = []
        for url in urls:
            try:
                records.append(load_product(url))
            except (ValueError, requests.RequestException) as exc:
                st.warning(f"Не удалось загрузить {url}: {type(exc).__name__}")
        if not records:
            st.info("Нет доступных карточек. Данные не подменяются примерами.")
            return
        df = pd.DataFrame(records)
        st.dataframe(df, use_container_width=True, hide_index=True, column_config={"Ссылка": st.column_config.LinkColumn("Карточка")})
        st.download_button("Скачать реальные данные CSV", df.to_csv(index=False).encode("utf-8-sig"), "kaspi_products.csv", "text/csv")
        st.caption("Цена — опубликованное значение метаданных карточки, не гарантированная цена конкретного продавца.")
    st.divider()
    st.markdown("**Что ещё требуется для поиска реально продаваемых товаров**")
    st.write(
        "Полный охват категорий, данные о конкуренции, проверенные сигналы спроса, "
        "модель оценки продаж и проверка на фактических заказах. Эти данные пока не подключены."
    )
