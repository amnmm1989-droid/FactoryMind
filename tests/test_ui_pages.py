# tests/test_ui_pages.py
"""
اختبارات صفحات Phase 6.

لا تُصيّر Streamlit — ذلك عمل الـ driver
(.claude/skills/run-factorymind/driver.mjs). ما يُختبَر هنا هو المنطق
الذي يقرر *ماذا* تعرض الصفحة، وقد استُخرج ليكون قابلاً للاختبار: العتبات،
التنسيق، والتوقيعات التي يعتمد عليها app.py.

الاختباران الأولان يحرسان خطأين وجدهما التشغيل الحقيقي لا الاختبارات.
"""
from __future__ import annotations

import importlib

import pytest

from domain.entities import ProductionRecommendation, RiskLevel, RiskScore
from ui.pages.executive import (
    MIN_ACTIONABLE_UNITS,
    _format_quantity,
    _format_wape,
    _to_frame,
)

PAGE_MODULES = [
    "executive",
    "forecasting",
    "product_intelligence",
    "advanced_analytics",
    "purchase_plan",
]


# ---------------------------------------------------------------------------
# انحدارات وجدها التشغيل الحقيقي
# ---------------------------------------------------------------------------
def test_fractional_rates_are_not_displayed_as_zero():
    """انحدار: أول تشغيل أظهر 'أنتج 0' داخل جدول اسمه 'يحتاج قراراً'.

    Croston/TSB يُنتجان معدّلات كسرية (0.4 وحدة/شهر)، و round() كان
    يعرضها صفراً — تناقض ذاتي في الشاشة.
    """
    assert _format_quantity(0.4) == "0.4"
    assert _format_quantity(2.5) == "2.5"


def test_large_quantities_stay_readable():
    assert _format_quantity(1234.6) == "1,235"
    assert _format_quantity(48.0) == "48"


def test_actionable_threshold_excludes_sub_unit_rates():
    """أقل من نصف وحدة متوقَّعة = لا وحدة كاملة = لا قرار إنتاج."""
    assert MIN_ACTIONABLE_UNITS == 0.5
    assert 0.4 < MIN_ACTIONABLE_UNITS  # يُستبعد
    assert 0.6 >= MIN_ACTIONABLE_UNITS  # يُدرَج


# ---------------------------------------------------------------------------
# WAPE — عمود بجانب الثقة، لا يُستبدل بها
# ---------------------------------------------------------------------------
def test_wape_formats_as_a_rounded_percentage():
    assert _format_wape(12.3) == "12%"
    assert _format_wape(0.4) == "0%"


def test_unmeasured_wape_shows_a_dash_not_zero():
    """منتج بلا تقييم تاريخي (سلسلة قصيرة) ليس دقيقاً 0% — بل غير مقيس.
    نفس مبدأ None٪ في risk_service: المجهول لا يُعرَض كرقم حقيقي."""
    assert _format_wape(None) == "—"


def _recommendation(product="منتج", wape=None, fva=None) -> ProductionRecommendation:
    return ProductionRecommendation(
        product_name=product,
        recommended_quantity=100.0,
        reason="اختبار",
        expected_demand_change_pct=5.0,
        risk=RiskScore(
            product_name=product, score=40, demand_volatility=0.3,
            stock_depletion_risk=None, forecast_accuracy_penalty=0.2,
            seasonality_factor=0.1, growth_rate=0.05,
        ),
        forecast_wape=wape,
        forecast_fva=fva,
    )


def test_to_frame_carries_the_wape_column():
    from ui.i18n import t

    frame = _to_frame([_recommendation(wape=8.5)])

    assert t("common.wape") in frame.columns
    assert frame.iloc[0][t("common.wape")] == "8%"


def test_to_frame_shows_a_dash_when_wape_was_never_computed():
    from ui.i18n import t

    frame = _to_frame([_recommendation(wape=None)])

    assert frame.iloc[0][t("common.wape")] == "—"


def test_to_frame_carries_the_plain_language_reason_column():
    """رقم الخطورة وحده لا يشرح نفسه — عمود السبب يحمل الجملة المبنية من
    format_reason، لا يبقى غائباً كما كان قبل هذا التغيير."""
    from ui.i18n import t

    frame = _to_frame([_recommendation()])

    assert t("common.reason") in frame.columns
    assert frame.iloc[0][t("common.reason")] == "اختبار"


# ---------------------------------------------------------------------------
# انحدار وجده تشغيل حقيقي: اختيار قديم في session_state بعد رفع ملف جديد
# ---------------------------------------------------------------------------
def test_stale_selected_products_does_not_crash_the_sidebar():
    """رفع ملف جديد بمنتجات مختلفة تماماً بعد اختيار سابق محفوظ في
    session_state كان يرفع StreamlitAPIException — القيمة الافتراضية
    (منتج من الرفع السابق) لم تعد ضمن خيارات الرفع الجديد."""
    from streamlit.testing.v1 import AppTest

    def script() -> None:
        from ui.pages.advanced_analytics import render

        months = ["2026-01", "2026-02", "2026-03"]
        products = {"New Product A": [1.0, 2.0, 3.0], "New Product B": [4.0, 5.0, 6.0]}
        render(months, products)

    at = AppTest.from_function(script, default_timeout=30)
    at.session_state["selected_products"] = ["Bearing Assembly Type A"]
    at.run()

    assert not at.exception


# ---------------------------------------------------------------------------
# العقد مع app.py
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("module_name", PAGE_MODULES)
def test_every_page_is_importable(module_name):
    """app.py يستوردها كسولاً — خطأ استيراد يظهر عند النقر لا عند الإقلاع."""
    importlib.import_module(f"ui.pages.{module_name}")


@pytest.mark.parametrize("module_name", PAGE_MODULES)
def test_every_page_exposes_render(module_name):
    """التوقيع الموحّد render(months, products) — app.py يعتمد عليه."""
    module = importlib.import_module(f"ui.pages.{module_name}")

    assert callable(module.render)


@pytest.mark.parametrize("module_name", PAGE_MODULES)
def test_render_takes_months_and_products(module_name):
    import inspect

    module = importlib.import_module(f"ui.pages.{module_name}")

    parameters = list(inspect.signature(module.render).parameters)
    assert parameters == ["months", "products"]


def test_navigation_lists_every_page_with_a_unique_url():
    """انحدار: كل ما يُرجعه _page() اسمه `run`، فتشتقّ Streamlit المسار
    نفسه للصفحات الخمس وترفع StreamlitAPIException. url_path صريح إلزامي.
    """
    import re

    source = open("app.py", encoding="utf-8").read()
    paths = re.findall(r'url_path="([^"]+)"', source)

    assert len(paths) == len(PAGE_MODULES)
    assert len(set(paths)) == len(paths)


def test_every_page_module_is_wired_into_navigation():
    source = open("app.py", encoding="utf-8").read()

    for module_name in PAGE_MODULES:
        assert f'_page("{module_name}")' in source



# ---------------------------------------------------------------------------
# اكتمال عوامل الخطورة يُعرَض ككسر لا كنسبة — ولماذا
# ---------------------------------------------------------------------------
def test_risk_factor_completeness_is_shown_as_a_fraction_not_a_percentage():
    """RiskScore.confidence تعدّ العوامل المحسوبة، لا تقيس ثقةً في التنبؤ.

    عرضها «60%» بجانب عمود «دقّة WAPE» في نفس الصف كان يُقرأ حتماً
    «التنبؤ موثوق 60%». الكسر «3/5» لا يحتمل تلك القراءة.
    """
    from ui.pages.executive import _format_factors

    risk = RiskScore(
        product_name="منتج", score=42.0,
        demand_volatility=50.0,
        stock_depletion_risk=None,          # مخزون مجهول
        forecast_accuracy_penalty=20.0,
        seasonality_factor=10.0,
        growth_rate=None,                   # تاريخ أقصر من أن يُقاس نموّه
    )

    assert risk.factor_counts == (3, 5)
    assert _format_factors(risk) == "3/5"
    assert "%" not in _format_factors(risk)


def test_the_factor_total_is_derived_not_hardcoded():
    """إضافة عامل سادس يجب ألا تترك «/5» كذبةً في الشاشة."""
    from ui.pages.executive import _format_factors

    complete = RiskScore(
        product_name="منتج", score=1.0, demand_volatility=1.0,
        stock_depletion_risk=1.0, forecast_accuracy_penalty=1.0,
        seasonality_factor=1.0, growth_rate=1.0,
    )
    known, total = complete.factor_counts

    assert known == total
    assert _format_factors(complete) == f"{total}/{total}"


def test_no_user_facing_label_calls_factor_completeness_confidence():
    """حارس التسمية: المفتاح القديم كان يقول «ثقة التقييم»."""
    from ui.i18n import STRINGS

    label = STRINGS["common.risk_factors"]
    assert "confidence" not in label["en"].lower()
    assert "ثقة" not in label["ar"]
