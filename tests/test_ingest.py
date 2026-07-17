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
    "Hydraulic Pump,120,95,130,110\n"
    "Safety Valve,45,0,60,30\n"
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
    assert dataset.products["Hydraulic Pump"] == [120.0, 95.0, 130.0, 110.0]


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
    assert any(w.code == "duplicate_rows" for w in dataset.warnings)


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
    assert any(w.code == "dropped_columns" for w in dataset.warnings)


def test_gaps_in_the_timeline_are_flagged():
    """الأشهر الناقصة ليست أصفاراً — هي غياب بيانات، والموسمية عليها كاذبة."""
    data = csv("p,يناير 2024,فبراير 2024,يونيو 2024\nA,1,2,3\n")

    dataset = parse_upload(data, "g.csv")

    assert any(w.code == "timeline_gaps" for w in dataset.warnings)


def test_a_continuous_timeline_raises_no_gap_warning():
    dataset = parse_upload(WIDE, "sales.csv")

    assert not any(w.code == "timeline_gaps" for w in dataset.warnings)


def test_negative_quantities_are_clipped_with_a_warning():
    """مرتجعات؟ المحرّكات تتعامل مع الطلب لا صافي الحركة."""
    data = csv("p,يناير 2024,فبراير 2024,مارس 2024\nA,10,-5,3\n")

    dataset = parse_upload(data, "n.csv")

    assert dataset.products["A"] == [10.0, 0.0, 3.0]
    assert any(w.code == "negatives" for w in dataset.warnings)


def test_non_numeric_cells_become_zero_with_a_warning():
    data = csv("p,يناير 2024,فبراير 2024,مارس 2024\nA,10,abc,3\n")

    dataset = parse_upload(data, "x.csv")

    assert dataset.products["A"] == [10.0, 0.0, 3.0]
    assert any(w.code == "non_numeric" for w in dataset.warnings)


def test_products_without_any_sales_are_flagged():
    data = csv("p,يناير 2024,فبراير 2024,مارس 2024\nA,1,2,3\nB,0,0,0\n")

    dataset = parse_upload(data, "d.csv")

    assert any(w.code == "dead_products" for w in dataset.warnings)


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


def test_forecast_months_continue_past_the_last_month():
    """انحدار: كانت الدالة تلتفّ إلى بداية السلسلة (`% len(months)`).

    تنبؤ ما بعد "يوليو 2026" كان يُسمّى "ديسمبر 2022" — فتُرسَم نقاط
    التنبؤ على مواضع تاريخية وتصطدم بها على محور فئوي. الاختبار الوحيد
    آنذاك كان يفحص الطول، فمرّ الخطأ. كشفه بحثٌ عن نصوص غير مترجَمة.
    """
    from services.analytics import prepare_forecast_months

    months = ["مايو 2026", "يونيو 2026", "يوليو 2026"]

    assert prepare_forecast_months(2, months, 3) == ["2026-08", "2026-09", "2026-10"]


def test_forecast_months_roll_over_the_year():
    from services.analytics import prepare_forecast_months

    months = ["نوفمبر 2025", "ديسمبر 2025"]

    assert prepare_forecast_months(1, months, 2) == ["2026-01", "2026-02"]


def test_unparseable_last_month_yields_explicit_offsets():
    """تسمية مخصّصة من ملف مستخدم: "+1" صريحة في أنها إزاحة، بينما
    تاريخ مخترَع يبدو حقيقة."""
    from services.analytics import prepare_forecast_months

    assert prepare_forecast_months(0, ["W52"], 2) == ["+1", "+2"]


def test_the_template_is_parseable_by_the_parser_that_ships_with_it():
    """نموذج يرفضه محلّله لا يعلّم أحداً شيئاً."""
    dataset = parse_upload(to_csv_template(), "template.csv")

    assert isinstance(dataset, Dataset)
    assert dataset.product_count == 2
    assert all(w.code != "dead_products" for w in dataset.warnings)


# ---------------------------------------------------------------------------
# بوابة الحبيبة الزمنية — الثقب الأخير في مبدأ "اعرف متى لا تعرف"
# ---------------------------------------------------------------------------
def _series(start: tuple, step_days: int, count: int) -> bytes:
    import datetime

    first = datetime.date(*start)
    header, row = "Product", "Widget"
    for i in range(count):
        header += f",{(first + datetime.timedelta(days=step_days * i)).isoformat()}"
        row += f",{100 + i % 5 * 20}"
    return f"{header}\n{row}\n".encode()


def test_full_dates_keep_the_day():
    """السبب الجذري: parse_month_label يقصّ اليوم، فتضيع الحبيبة قبل قياسها."""
    from services.ingest import parse_full_date

    assert parse_full_date("2025-01-13") == date(2025, 1, 13)
    assert parse_month_label("2025-01-13") == date(2025, 1, 1)


def test_a_month_name_without_a_day_starts_the_month():
    """بيانات شهرية لا يوم لها — الأول هو الصحيح لا اختراع."""
    from services.ingest import parse_full_date

    assert parse_full_date("يناير 2023") == date(2023, 1, 1)


@pytest.mark.parametrize("step,expected", [(1, "daily"), (7, "weekly")])
def test_sub_monthly_granularity_is_detected(step, expected):
    """تواريخ بيوم صريح: الفارق الأصغر هو الحبيبة."""
    import datetime

    from services.ingest import detect_granularity

    first = datetime.date(2024, 1, 3)   # ليس أول الشهر — يوم صريح
    dates = [first + datetime.timedelta(days=step * i) for i in range(8)]

    assert detect_granularity(dates) == expected


def test_a_label_without_a_day_cannot_be_finer_than_monthly():
    """القاعدة التي تُنقذ البيانات المتقطّعة.

    "يناير 2024" لا يحمل يوماً — فهو شهري بحكم بنيته مهما تباعد. بيانات
    شهرية بفجوات كبيرة (يناير، يونيو، ديسمبر) فوارقها 152 و183 يوماً،
    وأي تصنيف بالفوارق وحدها يسمّيها "ربعية" ويرفضها خطأً — و84% من هذا
    الكتالوج متقطّع، أي يُصدَّر بأشهر ناقصة.
    """
    from services.ingest import detect_granularity

    sparse = [date(2024, 1, 1), date(2024, 6, 1), date(2024, 12, 1)]

    assert detect_granularity(sparse) == "monthly"


def test_gaps_do_not_fool_the_detector():
    from services.ingest import detect_granularity

    dates = [date(2024, 1, 1), date(2024, 2, 1), date(2024, 6, 1), date(2024, 7, 1)]

    assert detect_granularity(dates) == "monthly"


def test_weekly_dates_with_a_gap_are_still_weekly():
    """الفجوات مضاعفات للحبيبة لا حبيبة أخرى: 7، 14، 7 -> الأصغر هو الحقيقة."""
    from services.ingest import detect_granularity

    dates = [date(2025, 1, 6), date(2025, 1, 13), date(2025, 1, 27), date(2025, 2, 3)]

    assert detect_granularity(dates) == "weekly"


def test_a_single_date_has_no_measurable_granularity():
    from services.ingest import detect_granularity

    assert detect_granularity([date(2024, 1, 1)]) is None


def test_identical_labels_measure_nothing():
    from services.ingest import detect_granularity

    assert detect_granularity([date(2024, 1, 1)] * 3) is None


def test_weekly_data_is_rejected_not_silently_treated_as_monthly():
    """الانحدار الأساسي لهذه المرحلة.

    قبل البوابة: 30 أسبوعاً تُقبل وتُقرأ 30 شهراً، وSEASONAL_PERIODS=12
    يبحث عن دورة كل 12 *أسبوعاً* ويسمّيها سنوية. لا خطأ يظهر — فقط
    تحليل واثق وخاطئ، والتحذير الوحيد (timeline_gaps) مضلّل: لا فجوات.
    """
    with pytest.raises(DataValidationError) as excinfo:
        parse_upload(_series((2025, 1, 6), 7, 30), "weekly.csv")

    assert excinfo.value.context["code"] == "unsupported_granularity"
    assert excinfo.value.context["granularity"] == "weekly"


def test_daily_data_is_rejected_too():
    with pytest.raises(DataValidationError) as excinfo:
        parse_upload(_series((2024, 1, 3), 1, 20), "daily.csv")

    assert excinfo.value.context["granularity"] == "daily"


def test_monthly_data_still_passes():
    """البوابة تحرس ولا تمنع: بيانات المشروع نفسها يجب أن تمرّ."""
    dataset = parse_upload(_series((2023, 1, 1), 31, 24), "monthly.csv")

    assert dataset.month_count == 24


def test_mid_month_dates_are_still_monthly():
    """تصديرة بتاريخ منتصف الشهر (2024-01-15، 2024-02-15) شهرية رغم اليوم."""
    dataset = parse_upload(_series((2024, 1, 15), 31, 12), "mid.csv")

    assert dataset.month_count == 12


def test_arabic_monthly_labels_still_pass():
    dataset = parse_upload(WIDE, "sales.csv")

    assert dataset.month_count == 4


def test_gapped_monthly_data_is_not_rejected():
    """فجوة في البيانات ليست حبيبة مختلفة — تُحذَّر ولا تُرفَض."""
    data = csv("p,يناير 2024,فبراير 2024,يونيو 2024,يوليو 2024\nA,1,2,3,4\n")

    dataset = parse_upload(data, "g.csv")

    assert dataset.month_count == 4
    assert any(w.code == "timeline_gaps" for w in dataset.warnings)
