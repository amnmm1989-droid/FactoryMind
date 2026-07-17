# tests/test_customer_analysis.py
"""
اختبارات services/customer_analysis.py — تركّز، نمو، عملاء ينزفون.

بلا Streamlit: حساب بحت على CustomerSalesDataset، والمبدأ الحاكم كبقية
هذا المشروع: نسبة غير معرَّفة رياضياً (قسمة على صفر) تُعاد None أو تُستبعد
بدل رقم مخترَع يبدو دقيقاً.
"""
from __future__ import annotations

import pytest

from services.customer_analysis import (
    BLEEDING_THRESHOLD_PCT,
    bleeding_customers,
    concentration,
    growth_by_customer,
)
from services.ingest import CustomerSalesDataset


def _dataset(rows: dict[str, dict[str, list[float]]], months: list[str]) -> CustomerSalesDataset:
    return CustomerSalesDataset(months=months, rows=rows)


# ---------------------------------------------------------------------------
# التركّز
# ---------------------------------------------------------------------------
def test_concentration_ranks_customers_by_share_descending():
    dataset = _dataset(
        {"ACME": {"Pump": [80.0, 50.0]}, "Delta": {"Pump": [20.0, 15.0]}},
        months=["Jan", "Feb"],
    )

    rows = concentration(dataset)

    assert [r.customer for r in rows] == ["ACME", "Delta"]
    assert rows[0].quantity == 130.0
    assert rows[0].share_pct == pytest.approx(130 / 165 * 100)
    assert rows[-1].cumulative_share_pct == pytest.approx(100.0)


def test_concentration_sums_quantity_across_products_for_the_same_customer():
    dataset = _dataset(
        {"ACME": {"Pump": [50.0], "Valve": [50.0]}},
        months=["Jan"],
    )

    rows = concentration(dataset)

    assert rows[0].quantity == 100.0
    assert rows[0].share_pct == pytest.approx(100.0)


def test_concentration_on_all_zero_quantity_is_empty_not_undefined_shares():
    """إجمالي صفر يعني حصصاً غير معرَّفة (0/0) — قائمة فارغة لا نِسَب مخترَعة."""
    dataset = _dataset({"ACME": {"Pump": [0.0, 0.0]}}, months=["Jan", "Feb"])

    assert concentration(dataset) == []


def test_concentration_on_no_customers_is_empty():
    assert concentration(_dataset({}, months=["Jan", "Feb"])) == []


# ---------------------------------------------------------------------------
# النمو
# ---------------------------------------------------------------------------
def test_growth_compares_second_half_average_to_first_half():
    dataset = _dataset(
        {"ACME": {"Pump": [100.0, 100.0, 20.0, 20.0]}}, months=["Jan", "Feb", "Mar", "Apr"],
    )

    rows = growth_by_customer(dataset)

    assert rows[0].first_half_avg == 100.0
    assert rows[0].second_half_avg == 20.0
    assert rows[0].growth_pct == pytest.approx(-80.0)


def test_growth_with_two_months_compares_them_directly():
    dataset = _dataset({"ACME": {"Pump": [10.0, 15.0]}}, months=["Jan", "Feb"])

    rows = growth_by_customer(dataset)

    assert rows[0].growth_pct == pytest.approx(50.0)


def test_growth_from_a_zero_first_half_is_none_not_infinite_or_zero():
    """نمو من صفر غير معرَّف رياضياً — لا صفر ولا رقم مخترَع."""
    dataset = _dataset({"ACME": {"Pump": [0.0, 10.0]}}, months=["Jan", "Feb"])

    rows = growth_by_customer(dataset)

    assert rows[0].growth_pct is None
    assert rows[0].second_half_avg == 10.0


def test_positive_growth_is_reported_for_a_growing_customer():
    dataset = _dataset({"ACME": {"Pump": [10.0, 30.0]}}, months=["Jan", "Feb"])

    rows = growth_by_customer(dataset)

    assert rows[0].growth_pct == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# العملاء الذين ينزفون
# ---------------------------------------------------------------------------
def test_bleeding_flags_customers_below_the_threshold():
    dataset = _dataset(
        {
            "Bleeding": {"Pump": [100.0, 20.0]},   # -80%
            "Stable": {"Pump": [100.0, 95.0]},     # -5%
            "Growing": {"Pump": [10.0, 30.0]},     # +200%
        },
        months=["Jan", "Feb"],
    )

    result = bleeding_customers(dataset)

    assert [r.customer for r in result] == ["Bleeding"]


def test_bleeding_excludes_customers_with_undefined_growth():
    """عميل بلا مشتريات في النصف الأول لم يكن عميلاً بعد — ليس نازفاً."""
    dataset = _dataset({"New": {"Pump": [0.0, 10.0]}}, months=["Jan", "Feb"])

    assert bleeding_customers(dataset) == []


def test_bleeding_respects_a_custom_threshold():
    dataset = _dataset({"Mild": {"Pump": [100.0, 85.0]}}, months=["Jan", "Feb"])  # -15%

    assert bleeding_customers(dataset) == []
    assert bleeding_customers(dataset, threshold_pct=-10.0) != []


def test_bleeding_sorts_the_steepest_decline_first():
    dataset = _dataset(
        {
            "Mild": {"Pump": [100.0, 60.0]},    # -40%
            "Severe": {"Pump": [100.0, 10.0]},  # -90%
        },
        months=["Jan", "Feb"],
    )

    result = bleeding_customers(dataset)

    assert [r.customer for r in result] == ["Severe", "Mild"]


def test_default_threshold_matches_the_module_constant():
    assert BLEEDING_THRESHOLD_PCT == -20.0
