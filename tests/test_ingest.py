# tests/test_ingest.py
"""
اختبارات قراءة ملفات المستخدم.

المحور: الملفات الحقيقية وسخة. القاعدة أن الوسخ يُرفَض أو يُحذَّر منه
صراحةً — ولا يُصحَّح بصمت، لأن رقماً خاطئاً يبدو صحيحاً أخطر من رفض.
"""
from __future__ import annotations

from datetime import date

import pytest

from core.exceptions import DataValidationError
from services.ingest import Dataset, parse_month_label, parse_upload, to_csv_template


def csv(text: str) -> bytes:
    return text.encode("utf-8")


WIDE = csv(
    "المنتج,يناير 2024,فبراير 2024,مارس 2024,أبريل 2024\n"
    "بنّ برازيلي,120,95,130,110\n"
    "بنّ إثيوبي,45,0,60,30\n"
)
LONG = csv(
    "product,month,quantity\n"
    "A,Jan 2024,10\nA,Feb 2024,20\nA,Mar 2024,30\n"
    "B,Jan 2024,5\nB,Feb 2024,5\nB,Mar 2024,5\n"
)


# ---------------------------------------------------------------------------
# تحليل تسميات الأشهر
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("label,expected", [
    ("يناير 2023", date(2023, 1, 1)),
    ("ديسمبر 2022", date(2022, 12, 1)),
    ("كانون الثاني 2023", date(2023, 1, 1)),   # التسمية الشامية
    ("أكتوبر 2024", date(2024, 10, 1)),
    ("اكتوبر 2024", date(2024, 10, 1)),        # بلا همزة
    ("Jan 2023", date(2023, 1, 1)),
    ("2023-01", date(2023, 1, 1)),
    ("2023-01-15", date(2023, 1, 1)),          # اليوم يُهمَل — الحبيبة شهرية
])
def test_understood_month_labels(label, expected):
    assert parse_month_label(label) == expected


@pytest.mark.parametrize("label", ["الشهر الأول", "P1", "أسبوع 3", "Q1", "", "إجمالي"])
def test_unreadable_labels_return_none_rather_than_a_guess(label):
    """تخمين 'Q1' كشهر يُنتج موسمية على تقويم مخترع — الرفض أصدق."""
    assert parse_month_label(label) is None


def test_arabic_month_without_a_year_is_rejected():
    assert parse_month_label("يناير") is None


# ---------------------------------------------------------------------------
# الشكل العريض — مخرج Excel/ERP المعتاد
# ---------------------------------------------------------------------------
def test_wide_layout_is_read():
    dataset = parse_upload(WIDE, "sales.csv")

    assert dataset.product_count == 2
    assert dataset.month_count == 4
    assert dataset.products["بنّ برازيلي"] == [120.0, 95.0, 130.0, 110.0]


def test_start_date_comes_from_the_file_not_a_constant():
    dataset = parse_upload(WIDE, "sales.csv")

    assert dataset.start_date == date(2024, 1, 1)


# ---------------------------------------------------------------------------
# الشكل الطويل — مخرج قواعد البيانات
# ---------------------------------------------------------------------------
def test_long_layout_is_detected_and_pivoted():
    dataset = parse_upload(LONG, "sales.csv")

    assert dataset.products == {"A": [10.0, 20.0, 30.0], "B": [5.0, 5.0, 5.0]}


def test_duplicate_rows_are_summed_not_dropped():
    """صفّان لنفس المنتج/الشهر = طلبان. أخذ الأول يفقد مبيعات."""
    data = csv(
        "product,month,quantity\n"
        "A,Jan 2024,10\nA,Jan 2024,15\nA,Feb 2024,20\nA,Mar 2024,5\n"
    )

    dataset = parse_upload(data, "d.csv")

    assert dataset.products["A"][0] == 25.0
    assert any("مكرّر" in w for w in dataset.warnings)


# ---------------------------------------------------------------------------
# الترتيب الزمني
# ---------------------------------------------------------------------------
def test_months_are_ordered_by_date_not_by_column_position():
    """عمود 'يناير' قبل 'ديسمبر' في الملف يعني سنة تالية لا شهراً سابقاً.

    الأخذ بترتيب الملف يقلب السلسلة الزمنية — وكل تنبؤ بعدها بلا معنى.
    """
    data = csv("p,ديسمبر 2024,يناير 2024,يونيو 2024\nX,3,1,2\n")

    dataset = parse_upload(data, "m.csv")

    assert dataset.months == ["يناير 2024", "يونيو 2024", "ديسمبر 2024"]
    assert dataset.products["X"] == [1.0, 2.0, 3.0]


def test_january_of_the_next_year_sorts_after_december():
    data = csv("p,نوفمبر 2023,ديسمبر 2023,يناير 2024\nX,1,2,3\n")

    dataset = parse_upload(data, "m.csv")

    assert dataset.products["X"] == [1.0, 2.0, 3.0]


# ---------------------------------------------------------------------------
# الرفض الصريح
# ---------------------------------------------------------------------------
def test_a_file_without_understandable_months_is_rejected():
    with pytest.raises(DataValidationError, match="لم يُفهَم أي عمود"):
        parse_upload(csv("p,Q1,Q2,Q3\nX,1,2,3\n"), "q.csv")


def test_too_few_months_is_rejected():
    with pytest.raises(DataValidationError, match="الحد الأدنى"):
        parse_upload(csv("p,يناير 2024,فبراير 2024\nX,1,2\n"), "s.csv")


def test_an_empty_file_is_rejected():
    with pytest.raises(DataValidationError, match="فارغ"):
        parse_upload(csv("p,m\n"), "e.csv")


def test_a_non_csv_file_is_rejected_with_a_readable_message():
    with pytest.raises(DataValidationError, match="تعذّرت قراءة الملف"):
        parse_upload(b"\x89PNG\r\n\x1a\n binary", "image.csv")


def test_a_file_with_no_valid_products_is_rejected():
    with pytest.raises(DataValidationError):
        parse_upload(csv("p,يناير 2024,فبراير 2024,مارس 2024\n"), "n.csv")


# ---------------------------------------------------------------------------
# التحذيرات — يُقبل الملف ويُقال ما فيه
# ---------------------------------------------------------------------------
def test_unreadable_columns_are_dropped_with_a_warning():
    data = csv("p,يناير 2024,فبراير 2024,مارس 2024,ملاحظات\nA,1,2,3,شيء\n")

    dataset = parse_upload(data, "w.csv")

    assert dataset.month_count == 3
    assert any("ملاحظات" in w for w in dataset.warnings)


def test_gaps_in_the_timeline_are_flagged():
    """الأشهر الناقصة ليست أصفاراً — هي غياب بيانات، والموسمية عليها كاذبة."""
    data = csv("p,يناير 2024,فبراير 2024,يونيو 2024\nA,1,2,3\n")

    dataset = parse_upload(data, "g.csv")

    assert any("فجوات" in w for w in dataset.warnings)


def test_a_continuous_timeline_raises_no_gap_warning():
    dataset = parse_upload(WIDE, "sales.csv")

    assert not any("فجوات" in w for w in dataset.warnings)


def test_negative_quantities_are_clipped_with_a_warning():
    """مرتجعات؟ المحرّكات تتعامل مع الطلب لا صافي الحركة."""
    data = csv("p,يناير 2024,فبراير 2024,مارس 2024\nA,10,-5,3\n")

    dataset = parse_upload(data, "n.csv")

    assert dataset.products["A"] == [10.0, 0.0, 3.0]
    assert any("سالبة" in w for w in dataset.warnings)


def test_non_numeric_cells_become_zero_with_a_warning():
    data = csv("p,يناير 2024,فبراير 2024,مارس 2024\nA,10,abc,3\n")

    dataset = parse_upload(data, "x.csv")

    assert dataset.products["A"] == [10.0, 0.0, 3.0]
    assert any("غير رقمية" in w for w in dataset.warnings)


def test_products_without_any_sales_are_flagged():
    data = csv("p,يناير 2024,فبراير 2024,مارس 2024\nA,1,2,3\nB,0,0,0\n")

    dataset = parse_upload(data, "d.csv")

    assert any("بلا أي مبيعات" in w for w in dataset.warnings)


def test_an_excel_bom_does_not_corrupt_the_first_column():
    """Excel يضع BOM على رأس CSV — بدون utf-8-sig يصير اسم العمود '\\ufeffالمنتج'."""
    dataset = parse_upload(b"\xef\xbb\xbf" + WIDE, "excel.csv")

    assert dataset.product_count == 2


# ---------------------------------------------------------------------------
# التكامل مع المحرّكات
# ---------------------------------------------------------------------------
def test_an_uploaded_dataset_feeds_the_forecast_engine():
    """العقد: ما يخرج من ingest يدخل المحرك بلا تحويل."""
    from services.forecast_engine import forecast_product
    from services.forecast_engine.naive import NaiveForecaster

    dataset = parse_upload(WIDE, "sales.csv")
    name, series = next(iter(dataset.products.items()))

    result = forecast_product(name, series, steps=2, models=[NaiveForecaster()],
                              use_cache=False)

    assert len(result.best.forecast_values) == 2


def test_the_template_is_parseable_by_the_parser_that_ships_with_it():
    """نموذج يرفضه محلّله لا يعلّم أحداً شيئاً."""
    dataset = parse_upload(to_csv_template(), "template.csv")

    assert isinstance(dataset, Dataset)
    assert dataset.product_count == 2
    assert dataset.warnings == [] or all("بلا أي مبيعات" not in w for w in dataset.warnings)
