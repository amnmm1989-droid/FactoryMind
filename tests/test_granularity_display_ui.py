# tests/test_granularity_display_ui.py
"""الصفحات تعرض حبيبة الملف الحقيقية لا "شهراً" ثابتة — مدفوعة عبر AppTest.

الانحدار المحروس هنا وجده طلب صريح: "تأكد أن كل الصفحات تعرض الحبيبة
الصحيحة للملفات الخمسة". قبل هذا كانت صفحة التنبؤ تقول "Forecast horizon
(months)" و"Next month forecast"، وذكاء المنتج "Months with sales"،
مهما كانت حبيبة الملف — أسبوعياً كان أم ربعياً أم سنوياً.

تُحقَن الحبيبة عبر session_state (نفس ما يفعله ui/data_source.py بعد رفع
ملف حقيقي)، فتقرأها الصفحات من active_granularity().
"""
from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from services.ingest import parse_upload
from ui.data_source import SESSION_KEY


def _dataset(gran: str):
    files = {
        "weekly": "Product," + ",".join(f"W{i} 2023" for i in range(1, 13)) + "\n"
                  + "Widget," + ",".join(str(10 + i) for i in range(12)) + "\n",
        "quarterly": "Product,Q1 2023,Q2 2023,Q3 2023,Q4 2023,Q1 2024,Q2 2024\n"
                     + "Widget," + ",".join(str(10 + i) for i in range(6)) + "\n",
        "yearly": "Product,2019,2020,2021,2022,2023\n"
                  + "Widget," + ",".join(str(10 + i) for i in range(5)) + "\n",
    }
    ds = parse_upload(files[gran].encode(), f"{gran}.csv")
    assert ds.granularity == gran  # الحبيبة اكتُشفت فعلاً قبل أن تُعرَض
    return ds


def _render(page_module: str, gran: str) -> AppTest:
    def script() -> None:
        import importlib

        import streamlit as st
        ds = st.session_state["_ds"]
        importlib.import_module(st.session_state["_page"]).render(
            ds.months, ds.products
        )

    ds = _dataset(gran)
    at = AppTest.from_function(script, default_timeout=90)
    at.session_state[SESSION_KEY] = ds
    at.session_state["_ds"] = ds
    at.session_state["_page"] = page_module
    at.run()
    assert not at.exception
    return at


@pytest.mark.parametrize("gran,unit", [
    ("weekly", "weeks"), ("quarterly", "quarters"), ("yearly", "years"),
])
def test_forecast_horizon_slider_names_the_files_unit(gran, unit):
    at = _render("ui.pages.forecasting", gran)

    labels = " ".join(s.label for s in at.slider)
    assert unit in labels
    assert "months" not in labels


@pytest.mark.parametrize("gran", ["weekly", "quarterly", "yearly"])
def test_next_period_metric_is_not_worded_as_month(gran):
    at = _render("ui.pages.forecasting", gran)

    metric_labels = [m.label for m in at.metric]
    assert "Next-period forecast" in metric_labels
    assert "Next month forecast" not in metric_labels


@pytest.mark.parametrize("gran,unit", [
    ("weekly", "Weeks"), ("quarterly", "Quarters"), ("yearly", "Years"),
])
def test_product_intelligence_selling_periods_names_the_unit(gran, unit):
    at = _render("ui.pages.product_intelligence", gran)

    metric_labels = " ".join(m.label for m in at.metric)
    assert f"{unit} with sales" in metric_labels
    assert "Months with sales" not in metric_labels


@pytest.mark.parametrize("gran,unit", [
    ("weekly", "weeks"), ("quarterly", "quarters"), ("yearly", "years"),
])
def test_purchase_plan_horizon_names_the_files_unit(gran, unit):
    at = _render("ui.pages.purchase_plan", gran)

    slider_and_number = " ".join(n.label for n in at.number_input)
    captions = " ".join(c.value for c in at.caption)
    assert unit in slider_and_number or unit in captions
    assert "months" not in slider_and_number
