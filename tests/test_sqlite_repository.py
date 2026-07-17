"""
اختبارات مستودع SQLite.

تفحص **العقد** لا شكل بيانات العرض: أن ما يُقرأ من القاعدة يطابق المصدر
الذي رُحِّل منه. الصيغة السابقة كانت تثبّت أعداداً حرفياً، فكانت
تفشل بمجرد تغيير الملف المرفق — وهو ما حدث حين استُبدلت بيانات حقيقية
ببيانات اصطناعية. عدد منتجات العرض ليس عقداً يستحق الحراسة؛ **مطابقة
الترحيل** هي العقد.
"""
import json

import pytest

from config import DATA_FILE


@pytest.fixture(scope="module")
def source() -> dict:
    """المصدر الذي رُحِّلت منه القاعدة — مرجع المقارنة."""
    with open(DATA_FILE, encoding="utf-8") as handle:
        return json.load(handle)


def test_months_match_the_source(repo, source):
    assert repo.get_months() == source["months"]


def test_every_product_is_migrated(repo, source):
    assert set(repo.get_products()) == set(source["products"])


def test_product_series_keeps_its_length(repo, source):
    product = repo.get_products()[0]

    assert len(repo.get_product_data(product)) == len(source["months"])


def test_product_values_survive_the_round_trip(repo, source):
    """الترحيل يجب ألا يغيّر رقماً — وإلا فكل تحليل بعده مبنيّ على وهم."""
    product = repo.get_products()[0]

    assert repo.get_product_data(product) == pytest.approx(source["products"][product])


def test_load_data_returns_the_whole_catalogue(repo, source):
    months, products = repo.load_data()

    assert months == source["months"]
    assert set(products) == set(source["products"])


def test_metadata_counts_match_the_source(repo, source):
    meta = repo.get_metadata()

    assert meta["total_months"] == len(source["months"])
    assert meta["total_products"] == len(source["products"])


def test_metadata_separates_dead_products(repo, source):
    """بيانات العرض تتضمّن منتجاً بلا مبيعات عمداً — ليُظهر الرفض الصريح."""
    expected_dead = sum(1 for values in source["products"].values() if sum(values) == 0)

    assert repo.get_metadata()["zero_products"] == expected_dead


# ---------------------------------------------------------------------------
# الفئات — products_meta.category، مصدرها data.json["categories"]
# ---------------------------------------------------------------------------
def test_categories_match_the_source(repo, source):
    """لا تخمين هنا: الفئة تُنقَل من JSON كما هي، فتطابقه حرفياً."""
    assert repo.get_categories() == source["categories"]


def test_every_categorized_product_is_a_real_product(repo, source):
    """لا فئة يتيمة لمنتج غير موجود — الترحيل يمرّ بمنتجات حقيقية فقط."""
    assert set(repo.get_categories()) <= set(source["products"])


def test_uncategorized_products_are_absent_not_null(repo, source):
    """منتج بلا فئة في المصدر غائب عن get_categories() تماماً — لا يظهر
    بقيمة None، ولا يُحتسب لاحقاً في فئة مخترعة (services/reconciliation)."""
    uncategorized = set(source["products"]) - set(source["categories"])
    if not uncategorized:
        pytest.skip("كل منتجات بيانات العرض مصنَّفة اليوم")

    categories = repo.get_categories()
    for product in uncategorized:
        assert product not in categories
