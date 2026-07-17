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
from ui.pages.production_planning import _adherence_summary_params
from ui.pages.executive import (
    MIN_ACTIONABLE_UNITS,
    _format_quantity,
    _format_wape,
    _to_frame,
)

PAGE_MODULES = [
    "executive",
    "forecasting",
    "production_planning",
    "product_intelligence",
    "advanced_analytics",
    "customer_intelligence",
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
# لوحة الالتزام (production_planning.py) — حساب بلا Streamlit
# ---------------------------------------------------------------------------
def test_no_judged_plans_gives_none_not_a_division_by_zero():
    """كل الخطط بلا توصية مرتبطة (أو لا خطط أصلاً) — لا 0/0."""
    assert _adherence_summary_params(
        {"total": 0, "followed": 0, "overridden": 0, "unlinked": 0}
    ) is None
    assert _adherence_summary_params(
        {"total": 5, "followed": 0, "overridden": 0, "unlinked": 5}
    ) is None


def test_the_percentage_excludes_unlinked_from_the_denominator():
    """جوهر الحساب: النسبة على judged = total - unlinked، لا على total.

    5 خطط، 2 منها بلا توصية مرتبطة: judged=3، والمتابعة من الثلاثة لا
    الخمسة — قسمتها على 5 كانت لتُصغِّر النسبة كذباً.
    """
    params = _adherence_summary_params(
        {"total": 5, "followed": 2, "overridden": 1, "unlinked": 2}
    )

    assert params["judged"] == 3
    assert params["pct"] == pytest.approx(2 / 3 * 100)


def test_fully_followed_reports_100_percent():
    params = _adherence_summary_params(
        {"total": 3, "followed": 3, "overridden": 0, "unlinked": 0}
    )

    assert params["pct"] == pytest.approx(100.0)


def test_fully_overridden_reports_zero_percent():
    params = _adherence_summary_params(
        {"total": 2, "followed": 0, "overridden": 2, "unlinked": 0}
    )

    assert params["pct"] == pytest.approx(0.0)
