# tests/test_default_product_selection.py
"""
ما تفتح عليه الصفحات ذات المنتج الواحد.

## العطل الذي تحرسه هذه الاختبارات

Forecasting و Product Intelligence و Advanced Analytics كانت تبني قائمة
المنتجات بـ`sorted(products)`، فتفتح كلّها على أول اسم أبجدياً. على
الكتالوج الحقيقي (185 منتجاً، خمسة ملفات ERP) ذلك المنتج
`Brazil - Morada () (60g)`:

| الملف | حجمه | أول فتح |
|---|---|---|
| يومي | 0.03% — #86 | يعمل |
| أسبوعي | 0.02% — #88 | يعمل |
| شهري | 0.03% — #86 | تحذير "لم يُقيَّم أي نموذج" |
| ربعي | 0.03% — #86 | تحذير |
| سنوي | **0% — منتج ميت** | **خطأ أحمر / صفحة فارغة** |

أكبر منتج (15.8% من الإنتاج) لا يراه أحد ما لم يبحث عنه بالاسم.
"""
from __future__ import annotations

from ui.data_source import products_by_volume

# كتالوج بشكل الكتالوج الحقيقي: الاسم الأبجدي الأول هو الأصغر حجماً
CATALOGUE = {
    "Brazil - Morada (60g)": [0.0, 1.0, 0.0, 2.0],       # أبجدياً أولاً، حجماً آخِراً
    "Ethiopia - Hambela (1/4kg)": [900.0, 1100.0, 950.0, 1050.0],
    "Yemen - Haraz (1kg)": [400.0, 380.0, 420.0, 400.0],
}


def test_the_biggest_product_comes_first_not_the_alphabetical_one():
    """الافتراضي في كل صفحة هو العنصر الأول — فترتيبه هو الإصلاح كلّه."""
    assert products_by_volume(CATALOGUE)[0] == "Ethiopia - Hambela (1/4kg)"


def test_the_whole_list_is_ordered_by_volume():
    """ليس الافتراضي وحده: التصفّح نفسه يجب أن يبدأ بما يهمّ."""
    assert products_by_volume(CATALOGUE) == [
        "Ethiopia - Hambela (1/4kg)",
        "Yemen - Haraz (1kg)",
        "Brazil - Morada (60g)",
    ]


def test_no_product_is_dropped():
    """قائمة اختيار ناقصة أسوأ من قائمة سيئة الترتيب."""
    assert set(products_by_volume(CATALOGUE)) == set(CATALOGUE)


def test_a_dead_product_sinks_to_the_bottom():
    """المنتج الميت هو ما كان يُصيَّر خطأً أحمر على الملف السنوي."""
    catalogue = dict(CATALOGUE, dead=[0.0, 0.0, 0.0, 0.0])

    assert products_by_volume(catalogue)[-1] == "dead"


def test_ties_are_broken_alphabetically_so_the_order_is_stable():
    """قائمة تتبدّل ترتيباً بين تشغيلين تُربك من يعود إليها."""
    tied = {"b": [5.0], "a": [5.0], "c": [5.0]}

    assert products_by_volume(tied) == ["a", "b", "c"]


def test_an_empty_catalogue_returns_an_empty_list_not_an_error():
    assert products_by_volume({}) == []


# ---------------------------------------------------------------------------
# الصفحات الثلاث تستخدمه فعلاً — لا تعود إلى sorted() بصمت
# ---------------------------------------------------------------------------
def test_the_single_product_pages_do_not_sort_alphabetically():
    from pathlib import Path

    for page in ("forecasting.py", "product_intelligence.py", "advanced_analytics.py"):
        source = Path("ui/pages") / page
        text = source.read_text(encoding="utf-8")
        assert "products_by_volume" in text, f"{page} لا يرتّب بالحجم"
        assert "sorted(products)" not in text, f"{page} عاد إلى الترتيب الأبجدي"
