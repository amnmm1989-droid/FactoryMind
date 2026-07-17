# tests/test_runtime_mode.py
"""
اختبارات وضع التشغيل وبصمة البيانات.

`_dataset_signature` تحرس أخطر خطأ في هذه المرحلة: توصيات محسوبة على
بيانات العرض تبقى معروضة بعد أن يرفع المستخدم ملفه.
"""
from __future__ import annotations

import pytest

from core.runtime_mode import ENV_VAR, RuntimeMode, current_mode, is_hosted
from ui.pages.executive import _dataset_signature


# ---------------------------------------------------------------------------
# الوضع
# ---------------------------------------------------------------------------
def test_default_is_local(monkeypatch):
    """الأقل مفاجأة لمن يستنسخ المستودع ويشغّله."""
    monkeypatch.delenv(ENV_VAR, raising=False)

    assert current_mode() is RuntimeMode.LOCAL


def test_hosted_is_opt_in(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "hosted")

    assert current_mode() is RuntimeMode.HOSTED
    assert is_hosted()


def test_an_unknown_value_falls_back_to_local(monkeypatch):
    """قيمة مكتوبة خطأً يجب ألا تُفعّل وضعاً بالصدفة."""
    monkeypatch.setenv(ENV_VAR, "hostd")

    assert current_mode() is RuntimeMode.LOCAL


def test_the_value_is_case_insensitive(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "  HOSTED  ")

    assert is_hosted()


def test_only_local_persists():
    """الوضع المستضاف لا يكتب: نسخة واحدة تخدم كل الزوّار، وقاعدة
    البيانات ملف مشترك — الحفظ يعني تسريب بيانات زائر لآخر."""
    assert RuntimeMode.LOCAL.persists
    assert not RuntimeMode.HOSTED.persists


# ---------------------------------------------------------------------------
# بصمة البيانات — الانحدار الذي كشفته لقطة شاشة
# ---------------------------------------------------------------------------
def test_the_same_data_gives_the_same_signature():
    products = {"A": [1.0, 2.0], "B": [3.0]}

    assert _dataset_signature(products) == _dataset_signature(dict(products))


def test_a_different_product_set_changes_the_signature():
    """الانحدار: 185 صنف بنّ مقابل 3 منتجات مرفوعة.

    بدون البصمة كان الشريط يقول "ملفك: 3 منتجات" بينما الجدول يعرض
    الـ 185 — نتائج محسوبة قبل الرفع وبقيت في session_state. مرّ الخطأ
    من كل فحص آلي (النصوص كانت موجودة) وكشفته لقطة شاشة.
    """
    demo = {f"بنّ {i}": [1.0, 2.0] for i in range(185)}
    uploaded = {"مضخة": [1.0, 2.0], "صمام": [3.0, 4.0], "محرك": [5.0, 6.0]}

    assert _dataset_signature(demo) != _dataset_signature(uploaded)


def test_changed_values_change_the_signature():
    """نفس المنتجات بأرقام محدَّثة = ملف جديد = إعادة حساب."""
    before = {"A": [1.0, 2.0, 3.0]}
    after = {"A": [1.0, 2.0, 4.0]}

    assert _dataset_signature(before) != _dataset_signature(after)


def test_key_order_does_not_change_the_signature():
    """قواميس بترتيب مختلف = نفس البيانات = لا إعادة حساب بلا داعٍ."""
    first = {"A": [1.0], "B": [2.0]}
    second = {"B": [2.0], "A": [1.0]}

    assert _dataset_signature(first) == _dataset_signature(second)


def test_an_added_product_changes_the_signature():
    base = {"A": [1.0, 2.0]}
    extended = {"A": [1.0, 2.0], "B": [3.0, 4.0]}

    assert _dataset_signature(base) != _dataset_signature(extended)


def test_tiny_float_noise_does_not_change_the_signature():
    """التقريب إلى 4 منازل: فروق الفاصلة العائمة لا تُبطل حساباً صحيحاً."""
    first = {"A": [1.00001, 2.0]}
    second = {"A": [1.000012, 2.0]}

    assert _dataset_signature(first) == _dataset_signature(second)
