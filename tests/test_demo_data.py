"""
اختبارات بيانات العرض المرفقة.

بيانات العرض أول ما يراه كل زائر، والمستودع عام. هذان الشرطان يحكمان:

1. **اصطناعية.** أي ملف حقيقي هنا يعني نشر أرقام مبيعات — الأصناف
   والكميات الشهرية لسنوات. سرّ تجاري لا عيّنة. (الملف السابق كان بيانات
   عمل حقيقية، أُزيلت من المستودع وتاريخه.)
2. **شارحة.** الأداة تقوم على تصنيف الطلب؛ كتالوج بتصنيف واحد لا يُظهر
   لماذا بُنيت. كل تصنيف يجب أن يكون حاضراً.
"""
from __future__ import annotations

import json

import pytest

from config import DATA_FILE
from services.forecast_engine import classify_demand
from services.forecast_engine.intermittent import DemandClass


@pytest.fixture(scope="module")
def demo() -> dict:
    with open(DATA_FILE, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def classes(demo) -> dict[str, int]:
    counts: dict[str, int] = {}
    for series in demo["products"].values():
        name = classify_demand(series).demand_class.value
        counts[name] = counts.get(name, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# الكتالوج يشرح الأداة
# ---------------------------------------------------------------------------
def test_smooth_products_exist(classes):
    """بلا منتج منتظم لا يرى الزائر ETS/SARIMA يفوزان أبداً."""
    assert classes.get("smooth", 0) >= 3


def test_intermittent_products_exist(classes):
    """84% من الطلب الصناعي متقطّع — وهو مجال Croston/TSB."""
    assert classes.get("intermittent", 0) >= 3


def test_lumpy_products_exist(classes):
    assert classes.get("lumpy", 0) >= 1


def test_a_dead_product_exists(classes):
    """يُظهر الرفض الصريح: لا نموذج ينطبق — وهو ميزة لا عطل."""
    assert classes.get("dead", 0) >= 1


def test_the_catalogue_is_not_dominated_by_one_class(classes, demo):
    """كتالوج بتصنيف واحد لا يشرح شيئاً — وهذا ما كانت عليه البيانات
    الحقيقية السابقة (84% متقطّع)."""
    largest = max(classes.values())

    assert largest / len(demo["products"]) < 0.6


# ---------------------------------------------------------------------------
# اصطناعية لا حقيقية
# ---------------------------------------------------------------------------
def test_the_generator_ships_with_the_data():
    """المولّد في المستودع هو الدليل على أن البيانات اصطناعية."""
    from pathlib import Path

    assert Path("scripts/generate_demo_data.py").exists()


def test_regenerating_gives_the_same_catalogue(demo):
    """البذرة ثابتة: المخرج متطابق في كل تشغيل، فالاختبارات مستقرة."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path("scripts").resolve()))
    from generate_demo_data import build_catalogue, month_labels

    assert month_labels() == demo["months"]
    assert build_catalogue() == pytest.approx(demo["products"])


# ---------------------------------------------------------------------------
# صالحة للمحرّكات
# ---------------------------------------------------------------------------
def test_every_series_matches_the_month_count(demo):
    months = len(demo["months"])

    assert all(len(series) == months for series in demo["products"].values())


def test_no_negative_quantities(demo):
    assert all(v >= 0 for series in demo["products"].values() for v in series)


def test_the_demo_data_is_monthly(demo):
    """بوابة الحبيبة ترفض ما ليس شهرياً — وبيانات العرض يجب أن تمرّ منها."""
    from services.ingest import detect_granularity, parse_full_date

    dates = [parse_full_date(label) for label in demo["months"]]

    assert detect_granularity([d for d in dates if d]) == "monthly"


# ---------------------------------------------------------------------------
# لا أثر للبيانات الأصلية في أي نص يراه المستخدم
# ---------------------------------------------------------------------------
# مصطلحات ممنوعة في أي نص يراه المستخدم.
#
# عامة عمداً: النسخة الأولى من هذا الحارس عدّدت أسماء أصناف بعينها —
# فكان يكتب على بابه ما يحرسه. الأسماء اختفت من الكود، فحراستها بلا معنى.
# ما يعود فعلاً هو الوصف العام للكتالوج القديم — نوعه وحجمه — لا الاسم
# المفرد؛ وهو ما ظهر للمستخدم بعد استبدال البيانات. لذا المصطلحات أدناه
# هي أصغر مجموعة تمسك ذلك، ولا واحد منها اسم صنف.
FORBIDDEN_TERMS = ("coffee", "بنّ", "185")


def test_no_user_facing_string_mentions_the_original_data():
    """انحدار: القاموس ظلّ يصف البيانات القديمة بعد استبدالها.

    استُبدل الملف ونُقّي التاريخ، ثم بقي النص الذي *يصف* الملف يُعلن نوع
    البيانات وحجمها على كل زائر. تغيير البيانات بلا تغيير ما يصفها تسريب.
    """
    from ui.i18n import STRINGS

    offenders = [
        f"{key}[{lang}]"
        for key, entry in STRINGS.items()
        for lang, text in entry.items()
        if any(term.lower() in text.lower() for term in FORBIDDEN_TERMS)
    ]

    assert offenders == [], f"نصوص تذكر البيانات الأصلية: {offenders}"


def test_the_csv_template_uses_synthetic_names():
    """النموذج يُنزّله المستخدم فعلاً — فهو نص يراه لا تعليق داخلي."""
    from services.ingest import to_csv_template

    template = to_csv_template().decode("utf-8-sig")

    assert not any(term.lower() in template.lower() for term in FORBIDDEN_TERMS)


def test_the_demo_catalogue_uses_synthetic_names(demo):
    assert not any(
        term.lower() in name.lower()
        for name in demo["products"]
        for term in FORBIDDEN_TERMS
    )
