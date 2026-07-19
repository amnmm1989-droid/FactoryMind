# tests/test_executive_priority.py
"""
أولوية جدول «يحتاج قراراً» — الشاشة الأولى التي يفتحها مصنع.

## العطل الذي تحرسه هذه الاختبارات

كان الجدول مرتّباً بالخطورة وحدها. الخطورة نسبة بلا مقياس، فتتصدّر
المنتجات الصغيرة المتذبذبة (أكياس 60g في هذا الكتالوج) وتغرق أكبر
منتجات المصنع. قياس على الملفات الخمسة، 185 منتجاً لكلٍّ منها:

| الملف | تغطية الصفوف الخمسين للحجم | أكبر منتج |
|---|---|---|
| يومي | 74% | #48 — ظاهر |
| أسبوعي | 20% | #56 — **غائب** |
| شهري | 9% | #74 — **غائب** |
| ربعي | 11% | #84 — **غائب** |
| سنوي | **6%** | #91 (86,967 وحدة) — **غائب** |

شاشةٌ عنوانها "يحتاج قراراً" تعرض 6% من الإنتاج ولا تعرض أكبر منتج
في المصنع ليست شاشة قرار.
"""
from __future__ import annotations

import pytest

from domain.entities import ProductionRecommendation, RiskScore
from ui.pages.executive import (
    ROWS_SHOWN,
    SORT_KEY,
    SORT_RISK,
    _format_wape,
    _prioritised,
)


def _risk(score: float) -> RiskScore:
    return RiskScore(
        product_name="x", score=score, demand_volatility=score,
        stock_depletion_risk=None, forecast_accuracy_penalty=None,
        seasonality_factor=None, growth_rate=None,
    )


def _rec(name: str, quantity: float, risk_score: float) -> ProductionRecommendation:
    return ProductionRecommendation(
        product_name=name, recommended_quantity=quantity, reason="",
        expected_demand_change_pct=0.0, risk=_risk(risk_score),
    )


# منتج المصنع الحقيقي مقابل كيس عيّنة متذبذب — الحالة التي قِيست
BIG_STEADY = _rec("كيس 1kg", 86_967, 30.0)
SMALL_ERRATIC = _rec("عيّنة 60g", 6.0, 75.0)


# ---------------------------------------------------------------------------
# الأثر: الكمية × الخطورة، بوحدات الإنتاج
# ---------------------------------------------------------------------------
def test_units_at_risk_is_in_production_units_not_a_unitless_index():
    """الرقم يجب أن يُقرأ كما هو: «كم وحدة معرَّضة؟»."""
    assert _rec("p", 1_000, 40.0).units_at_risk == pytest.approx(400.0)


def test_a_recommendation_without_a_risk_score_is_not_pushed_to_the_top():
    """خطورة مجهولة ليست خطورة قصوى — الافتراض المتشائم يزيح منتجاً
    مقيساً عن مكانه."""
    unscored = ProductionRecommendation(
        product_name="p", recommended_quantity=9_999, reason="",
        expected_demand_change_pct=0.0, risk=None,
    )

    assert unscored.units_at_risk == 0.0


# ---------------------------------------------------------------------------
# الترتيب الافتراضي
# ---------------------------------------------------------------------------
def test_the_biggest_product_outranks_a_volatile_sample_bag():
    """جوهر الإصلاح: 86,967 وحدة بخطورة 30 تسبق 6 وحدات بخطورة 75."""
    assert _prioritised([SMALL_ERRATIC, BIG_STEADY])[0] is BIG_STEADY


def test_the_shown_rows_cover_most_of_the_volume():
    """الحارس ضدّ الانتكاسة المقيسة: صفحةٌ تعرض ROWS_SHOWN صفاً ولا تغطّي
    إلا 6% من الحجم لا تُطلع من يقرأها على مصنعه.

    الكتالوج هنا يحاكي الشكل الحقيقي: قلّة كبيرة الحجم مستقرّة، وكثرة
    صغيرة متذبذبة — وهو ما يجعل الترتيب بالخطورة يفشل.
    """
    catalogue = (
        [_rec(f"كبير-{i}", 10_000 - i * 100, 25.0) for i in range(10)]
        + [_rec(f"صغير-{i}", 5.0, 70.0 + (i % 20) * 0.1) for i in range(120)]
    )
    total = sum(r.recommended_quantity for r in catalogue)

    shown = _prioritised(catalogue)[:ROWS_SHOWN]

    covered = sum(r.recommended_quantity for r in shown) / total
    assert covered > 0.70


# ---------------------------------------------------------------------------
# الترتيب بالخطورة يبقى متاحاً — لم يُحذف السؤال، غُيّر افتراضه
# ---------------------------------------------------------------------------
def test_risk_ordering_is_still_reachable(monkeypatch):
    import streamlit as st

    monkeypatch.setitem(st.session_state, SORT_KEY, SORT_RISK)

    assert _prioritised([BIG_STEADY, SMALL_ERRATIC])[0] is SMALL_ERRATIC


# ---------------------------------------------------------------------------
# WAPE: فوق الحدّ لا يُعرض الرقم الخام
# ---------------------------------------------------------------------------
def test_an_absurd_wape_is_capped_instead_of_printed_raw():
    """76,800% قِيست فعلاً على الملف السنوي. عرضها في عمود اسمه "الدقّة"
    يُفقد العمود مصداقيته."""
    assert _format_wape(76_800.0) == ">200%"
    assert _format_wape(21_149.0) == ">200%"


def test_a_measurable_wape_is_shown_as_it_is():
    assert _format_wape(47.0) == "47%"
    assert _format_wape(200.0) == "200%"


def test_an_unmeasured_wape_stays_an_em_dash_not_a_cap():
    """غير مقيس ≠ سيئ جداً — الخلط يخترع رقماً لم يُحسب."""
    assert _format_wape(None) == "—"
