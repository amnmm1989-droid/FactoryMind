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

from ui.pages.executive import MIN_ACTIONABLE_UNITS, _format_quantity

PAGE_MODULES = [
    "executive",
    "forecasting",
    "production_planning",
    "product_intelligence",
    "advanced_analytics",
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
