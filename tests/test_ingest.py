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
from services.ingest import (
    Dataset,
    customer_csv_template,
    guess_column,
    parse_actuals_upload,
    parse_actuals_upload_with_mapping,
    parse_customer_upload,
    parse_customer_upload_with_mapping,
    parse_month_label,
    parse_stock_upload,
    parse_stock_upload_with_mapping,
    parse_upload,
    parse_upload_with_mapping,
    read_columns,
    stock_csv_template,
    to_csv_template,
)


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


# ---------------------------------------------------------------------------
# فئة المنتج — عمود رابع اختياري، للتوفيق الهرمي فقط
# ---------------------------------------------------------------------------
def test_a_category_column_is_detected_and_carried_when_present():
    data = csv(
        "product,category,month,quantity\n"
        "A,Pumps,Jan 2024,10\nA,Pumps,Feb 2024,20\nA,Pumps,Mar 2024,30\n"
        "B,Valves,Jan 2024,5\nB,Valves,Feb 2024,5\nB,Valves,Mar 2024,5\n"
    )

    dataset = parse_upload(data, "cat.csv")

    assert dataset.categories == {"A": "Pumps", "B": "Valves"}
    assert dataset.products == {"A": [10.0, 20.0, 30.0], "B": [5.0, 5.0, 5.0]}


def test_no_category_column_gives_no_categories_not_an_error():
    """الغياب متوقَّع — معظم الملفات لن تحمل عمود فئة، ولا ينبغي أن يُرفَض."""
    dataset = parse_upload(LONG, "sales.csv")

    assert dataset.categories == {}


def test_a_wide_file_never_carries_categories():
    """لا عمود فئة ممكن هيكلياً في الشكل العريض — عمود أول واحد فهرس فقط."""
    dataset = parse_upload(WIDE, "sales.csv")

    assert dataset.categories == {}


def test_the_first_category_value_wins_when_rows_disagree():
    """الفئة صفة شبه ثابتة للمنتج — تضارب بين الصفوف يُحسم بالأول، لا يُرفَض."""
    data = csv(
        "product,category,month,quantity\n"
        "A,Pumps,Jan 2024,10\nA,PumpsV2,Feb 2024,20\nA,Pumps,Mar 2024,30\n"
    )

    dataset = parse_upload(data, "cat.csv")

    assert dataset.categories == {"A": "Pumps"}


def test_an_empty_category_cell_does_not_produce_an_empty_string_category():
    data = csv(
        "product,category,month,quantity\n"
        "A,,Jan 2024,10\nA,Pumps,Feb 2024,20\nA,Pumps,Mar 2024,30\n"
    )

    dataset = parse_upload(data, "cat.csv")

    assert dataset.categories == {"A": "Pumps"}


def test_manual_mapping_never_carries_categories():
    """شاشة الربط اليدوي (Phase 1) لا تعرض عموداً رابعاً للفئة اليوم —
    اكتشاف تلقائي فقط. توسيع مقصود لا سهو، موثَّق في READINESS_3_PLAN.md."""
    dataset = parse_upload_with_mapping(
        UNRECOGNIZED, "export.csv",
        product_column="Ident", month_column="Zeitraum", quantity_column="Betrag",
    )

    assert dataset.categories == {}


# ---------------------------------------------------------------------------
# تصديرات ERP الحقيقية — بأسماء أعمدتها لا بأسمائنا
# ---------------------------------------------------------------------------
# المشروع "طبقة تحليل فوق نظامك"، فأسماء أعمدة نظامك هي واجهته الحقيقية.
# كانت PRODUCT_HINTS تحمل "المادة" وتنسى أصلها "material"، فيسقط الشكل
# الطويل من SAP إلى _from_wide ويردّ "لم يُفهَم أي عمود كشهر" — خطأ يصف
# عرَضاً لا سبباً. مرّ ذلك بلا اختبار لأن كل اختبار هنا كان يستعمل
# أسماءنا نحن ("product"/"month"/"quantity") التي لا يصدّرها نظام أحد.
@pytest.mark.parametrize(
    "system, header",
    [
        ("SAP", "Material,Period,Quantity"),
        ("Odoo", "product_id,date,qty"),
        ("تصنيع عام", "Part Number,Month,Value"),
        ("عربية", "الصنف,الشهر,الكمية"),
    ],
)
def test_a_long_export_is_read_whatever_the_erp_calls_its_columns(system, header):
    data = csv(
        f"{header}\n"
        "PUMP-01,2024-01,10\nPUMP-01,2024-02,12\n"
        "PUMP-01,2024-03,9\nPUMP-01,2024-04,11\n"
    )

    dataset = parse_upload(data, "export.csv")

    assert dataset.products == {"PUMP-01": [10.0, 12.0, 9.0, 11.0]}, system


def test_a_wide_export_ignores_the_first_column_name():
    """الشكل العريض كان يعمل دائماً — وهذا سبب دقيق يستحق التثبيت.

    _from_wide يأخذ العمود الأول فهرساً بلا قراءة اسمه، فأي تسمية تمرّ.
    الـREADME كان يعلن أن SAP "تُرفض" بينما عريضها يُقبل منذ البداية:
    قيد موثَّق لا وجود له. هذا الاختبار يمنع عودة الادعاء.
    """
    data = csv("Material,2024-01,2024-02,2024-03\nPUMP-01,10,12,9\n")

    dataset = parse_upload(data, "sap.csv")

    assert dataset.products == {"PUMP-01": [10.0, 12.0, 9.0]}


# ---------------------------------------------------------------------------
# ربط الأعمدة يدوياً — حين يفشل التخمين تماماً
# ---------------------------------------------------------------------------
# لا كل تصديرة تحمل أسماء أعمدة نعرفها، ولن نضيف تلميحاً بالتخمين (راجع
# تعليق PRODUCT_HINTS في services/ingest.py). هذه الأعمدة مصطنعة عمداً —
# لا تطابق أي تلميح حالي — لإثبات أن المستخدم يستطيع إنقاذ ملفه بنفسه
# حين يفشل كل تخمين، لا حين يفشل تخمين بعينه فقط.
UNRECOGNIZED = csv(
    "Ident,Zeitraum,Betrag\n"
    "PUMP-01,2024-01,10\nPUMP-01,2024-02,12\n"
    "PUMP-01,2024-03,9\nPUMP-01,2024-04,11\n"
)


def test_automatic_parsing_fails_on_truly_unknown_column_names():
    """الحالة التي تحتاج ربطاً يدوياً: لا تخمين ينجح، ولا وهم بأنه نجح."""
    with pytest.raises(DataValidationError) as caught:
        parse_upload(UNRECOGNIZED, "export.csv")

    assert caught.value.context["code"] == "no_months"


def test_read_columns_exposes_the_files_actual_headers():
    """ما تعرضه شاشة الربط: أعمدة الملف كما هي، لا قائمة تلميحاتنا."""
    assert read_columns(UNRECOGNIZED, "export.csv") == ["Ident", "Zeitraum", "Betrag"]


def test_read_columns_rejects_an_empty_file_like_parse_upload_does():
    with pytest.raises(DataValidationError, match="فارغ"):
        read_columns(csv("p,m\n"), "e.csv")


@pytest.mark.parametrize(
    "role, expected",
    [("product", "product_id"), ("month", "date"), ("quantity", "qty")],
)
def test_guess_column_matches_known_hints(role, expected):
    columns = ["product_id", "date", "qty"]
    assert guess_column(columns, role) == expected


def test_guess_column_returns_none_for_unrecognized_names():
    """لا تخمين قسري — عمود لا يطابق أي تلميح يُترك للمستخدم صراحةً."""
    columns = ["Ident", "Zeitraum", "Betrag"]
    assert guess_column(columns, "product") is None
    assert guess_column(columns, "month") is None
    assert guess_column(columns, "quantity") is None


def test_manual_mapping_rescues_what_automatic_parsing_rejected():
    """الإثبات المحوري: نفس الملف الذي رفضه parse_upload يُقبل عبر
    parse_upload_with_mapping بمجرد أن يسمّي المستخدم أعمدته الثلاثة."""
    dataset = parse_upload_with_mapping(
        UNRECOGNIZED, "export.csv",
        product_column="Ident", month_column="Zeitraum", quantity_column="Betrag",
    )

    assert dataset.products == {"PUMP-01": [10.0, 12.0, 9.0, 11.0]}


def test_manual_mapping_tags_the_real_granularity_too():
    """الربط اليدوي يمرّ بـ_finalize نفسه — فيكتشف الحبيبة الحقيقية أيضاً،
    لا نسخة أخف منه تفترض الشهري صامتة."""
    weekly = csv(
        "Ident,Zeitraum,Betrag\n"
        "X,2024-01-01,1\nX,2024-01-08,2\nX,2024-01-15,3\nX,2024-01-22,4\n"
    )

    dataset = parse_upload_with_mapping(
        weekly, "w.csv",
        product_column="Ident", month_column="Zeitraum", quantity_column="Betrag",
    )

    assert dataset.granularity == "weekly"


def test_manual_mapping_still_flags_duplicate_rows():
    data = csv(
        "Ident,Zeitraum,Betrag\n"
        "A,Jan 2024,10\nA,Jan 2024,15\nA,Feb 2024,20\nA,Mar 2024,5\n"
    )

    dataset = parse_upload_with_mapping(
        data, "d.csv",
        product_column="Ident", month_column="Zeitraum", quantity_column="Betrag",
    )

    assert dataset.products["A"][0] == 25.0
    assert any(w.code == "duplicate_rows" for w in dataset.warnings)


def test_manual_mapping_rejects_a_column_that_does_not_exist():
    with pytest.raises(DataValidationError) as caught:
        parse_upload_with_mapping(
            UNRECOGNIZED, "export.csv",
            product_column="لا وجود له", month_column="Zeitraum",
            quantity_column="Betrag",
        )

    assert caught.value.context["code"] == "unknown_mapped_column"


def test_manual_mapping_rejects_the_same_column_for_two_roles():
    """عمود واحد لا يصلح لدورين — لا محور له معنى."""
    with pytest.raises(DataValidationError) as caught:
        parse_upload_with_mapping(
            UNRECOGNIZED, "export.csv",
            product_column="Ident", month_column="Ident", quantity_column="Betrag",
        )

    assert caught.value.context["code"] == "duplicate_mapped_columns"


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


def test_weekly_data_is_accepted_and_tagged_with_its_real_granularity():
    """الانحدار الأساسي لهذه المرحلة (قبل بند 1 من ROADMAP): 30 أسبوعاً
    كانت تُقرأ 30 شهراً، وSEASONAL_PERIODS=12 يبحث عن دورة كل 12 *أسبوعاً*
    ويسمّيها سنوية — تحليل واثق وخاطئ. الآن: يُقبَل ويُوسَم بحبيبته
    الحقيقية، فتشتقّ طبقات لاحقة (services/forecast_engine) الدورة
    الموسمية الصحيحة من dataset.granularity لا من ثابت شهري.
    """
    dataset = parse_upload(_series((2025, 1, 6), 7, 30), "weekly.csv")

    assert dataset.granularity == "weekly"
    assert dataset.month_count == 30


def test_daily_data_is_accepted_too():
    dataset = parse_upload(_series((2024, 1, 3), 1, 20), "daily.csv")

    assert dataset.granularity == "daily"


def test_quarterly_data_is_accepted_and_tagged():
    dataset = parse_upload(_series((2020, 1, 1), 91, 4), "quarterly.csv")

    assert dataset.granularity == "quarterly"


def test_yearly_data_is_accepted_and_tagged():
    dataset = parse_upload(_series((2015, 1, 1), 365, 4), "yearly.csv")

    assert dataset.granularity == "yearly"


def test_a_continuous_weekly_timeline_raises_no_false_gap_warning():
    """_expected_period_count يجب ألا يفترض شهراً لغير الشهري — سلسلة
    أسبوعية متصلة لا تستحق timeline_gaps."""
    dataset = parse_upload(_series((2025, 1, 6), 7, 10), "weekly.csv")

    assert not any(w.code == "timeline_gaps" for w in dataset.warnings)


def test_a_continuous_daily_timeline_raises_no_false_gap_warning():
    dataset = parse_upload(_series((2024, 1, 1), 1, 15), "daily.csv")

    assert not any(w.code == "timeline_gaps" for w in dataset.warnings)


def test_a_gap_in_a_weekly_timeline_is_still_flagged():
    """البوابة تكتشف الحبيبة، لكن الفجوات الحقيقية تبقى مرئية."""
    data = csv(
        "Product,2025-01-06,2025-01-13,2025-02-03\nWidget,10,20,30\n"
    )

    dataset = parse_upload(data, "gap.csv")

    assert dataset.granularity == "weekly"
    assert any(w.code == "timeline_gaps" for w in dataset.warnings)


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


# ---------------------------------------------------------------------------
# ملف المخزون — عمودان فقط، لقطة آنية لا سلسلة زمنية
# ---------------------------------------------------------------------------
STOCK_CSV = csv(
    "Product,Current Stock\n"
    "Hydraulic Pump,50\n"
    "Safety Valve,0\n"
)


def test_stock_file_is_read_by_hinted_column_names():
    snapshot = parse_stock_upload(STOCK_CSV, "stock.csv")

    assert snapshot.levels == {"Hydraulic Pump": 50.0, "Safety Valve": 0.0}
    assert snapshot.warnings == []


def test_stock_file_with_unrecognised_columns_names_the_missing_role():
    data = csv("Item Code,Value\nX,10\n")

    with pytest.raises(DataValidationError) as excinfo:
        parse_stock_upload(data, "weird.csv")

    assert excinfo.value.context["code"] == "no_stock_columns"


def test_stock_mapping_rescues_an_unrecognised_file():
    data = csv("Item Code,Value\nX,10\nY,20\n")

    snapshot = parse_stock_upload_with_mapping(
        data, "weird.csv", product_column="Item Code", stock_column="Value",
    )

    assert snapshot.levels == {"X": 10.0, "Y": 20.0}


def test_stock_mapping_rejects_the_same_column_for_both_roles():
    with pytest.raises(DataValidationError) as excinfo:
        parse_stock_upload_with_mapping(
            STOCK_CSV, "stock.csv",
            product_column="Product", stock_column="Product",
        )

    assert excinfo.value.context["code"] == "duplicate_mapped_columns"


def test_duplicate_product_rows_are_summed_not_overwritten():
    """صفّان لنفس المنتج غالباً مستودعان — مخزونهما الحقيقي مجموعهما."""
    data = csv("Product,Stock\nPump,30\nPump,20\n")

    snapshot = parse_stock_upload(data, "multi_warehouse.csv")

    assert snapshot.levels == {"Pump": 50.0}
    assert any(w.code == "stock_duplicate_rows" for w in snapshot.warnings)


def test_negative_stock_is_clipped_to_zero_and_warned():
    data = csv("Product,Stock\nPump,-5\n")

    snapshot = parse_stock_upload(data, "negative.csv")

    assert snapshot.levels == {"Pump": 0.0}
    assert any(w.code == "negatives" for w in snapshot.warnings)


def test_stock_template_has_the_two_expected_columns():
    import io

    import pandas as pd

    frame = pd.read_csv(io.BytesIO(stock_csv_template()), encoding="utf-8-sig")

    assert list(frame.columns) == ["المنتج", "المخزون الحالي"]


# ---------------------------------------------------------------------------
# ملف الإنتاج الفعلي — نفس شكل ملف المبيعات، بلا قيود السلسلة الزمنية
# ---------------------------------------------------------------------------
def test_a_single_month_is_accepted_unlike_the_sales_upload():
    """الفرق الجوهري عن parse_upload: شهر واحد هو الحالة الأشيع فعلياً —
    رفع الإنتاج الفعلي فور اكتمال الشهر، لا بعد تراكم ثلاثة."""
    data = csv("Product,Month,Quantity\nPump,Jan 2024,95\n")

    months, products = parse_actuals_upload(data, "one_month.csv")

    assert months == ["Jan 2024"]
    assert products == {"Pump": [95.0]}

    with pytest.raises(DataValidationError) as excinfo:
        parse_upload(data, "one_month.csv")
    assert excinfo.value.context["code"] == "too_few_months"


def test_a_genuine_wide_file_with_many_months_still_works():
    months, products = parse_actuals_upload(WIDE, "wide.csv")

    assert months == ["يناير 2024", "فبراير 2024", "مارس 2024", "أبريل 2024"]
    assert products["Hydraulic Pump"] == [120.0, 95.0, 130.0, 110.0]


def test_a_mislabeled_long_file_is_rejected_not_silently_treated_as_wide():
    """Ident/Zeitraum/Betrag لا تُلتقَط بالتلميحات ولا تُفسَّر كأشهر —
    نفس عطل SAP الطويل، فتُرفَض لا تُقرَأ خطأً كعريض بأعمدة عشوائية."""
    data = csv(
        "Ident,Zeitraum,Betrag\nPUMP-01,2024-01,10\nPUMP-01,2024-02,12\n"
    )

    with pytest.raises(DataValidationError) as excinfo:
        parse_actuals_upload(data, "sap.csv")

    assert excinfo.value.context["code"] == "no_actuals_columns"


def test_actuals_mapping_rescues_the_mislabeled_file():
    data = csv(
        "Ident,Zeitraum,Betrag\nPUMP-01,2024-01,10\nPUMP-01,2024-02,12\n"
    )

    months, products = parse_actuals_upload_with_mapping(
        data, "sap.csv",
        product_column="Ident", month_column="Zeitraum", quantity_column="Betrag",
    )

    assert products == {"PUMP-01": [10.0, 12.0]}
    assert set(months) == {"2024-01", "2024-02"}


def test_actuals_negative_quantities_are_clipped_to_zero():
    data = csv("Product,Month,Quantity\nPump,Jan 2024,-5\n")

    _, products = parse_actuals_upload(data, "negative.csv")

    assert products == {"Pump": [0.0]}


# ---------------------------------------------------------------------------
# ملف المبيعات حسب العميل — البُعد الثالث (product, customer, month, quantity)
# ---------------------------------------------------------------------------
CUSTOMER_CSV = csv(
    "Product,Customer,Month,Quantity\n"
    "Pump,ACME,Jan 2024,80\n"
    "Pump,Delta,Jan 2024,40\n"
    "Pump,ACME,Feb 2024,50\n"
    "Pump,Delta,Feb 2024,45\n"
    "Valve,ACME,Jan 2024,20\n"
    "Valve,ACME,Feb 2024,15\n"
)


def test_a_customer_file_is_read_by_hinted_column_names():
    dataset = parse_customer_upload(CUSTOMER_CSV, "customers.csv")

    assert dataset.months == ["Jan 2024", "Feb 2024"]
    assert dataset.rows == {
        "ACME": {"Pump": [80.0, 50.0], "Valve": [20.0, 15.0]},
        "Delta": {"Pump": [40.0, 45.0]},
    }
    assert dataset.customer_count == 2


def test_customer_totals_sum_across_products_per_month():
    dataset = parse_customer_upload(CUSTOMER_CSV, "customers.csv")

    assert dataset.customer_totals() == {
        "ACME": [100.0, 65.0],
        "Delta": [40.0, 45.0],
    }


def test_two_months_are_accepted_unlike_the_sales_upload_min_of_three():
    """CUSTOMER_MIN_MONTHS=2 لا MIN_MONTHS=3: التحليل يقارن نصفين، لا
    يبني تنبؤاً — نفس الدرس الذي كشفه ملف الإنتاج الفعلي."""
    data = csv(
        "Product,Customer,Month,Quantity\nPump,ACME,Jan 2024,10\nPump,ACME,Feb 2024,20\n"
    )

    dataset = parse_customer_upload(data, "two_months.csv")

    assert dataset.months == ["Jan 2024", "Feb 2024"]


def test_a_single_month_is_still_rejected():
    """شهر واحد لا يكفي لمقارنة نصفين — حتى بحدّ أدنى مخفَّف عن ملف المبيعات."""
    data = csv("Product,Customer,Month,Quantity\nPump,ACME,Jan 2024,10\n")

    with pytest.raises(DataValidationError) as excinfo:
        parse_customer_upload(data, "one_month.csv")

    assert excinfo.value.context["code"] == "too_few_months"
    assert excinfo.value.context["minimum"] == 2


def test_a_file_missing_the_customer_column_is_rejected_for_mapping():
    """نفس شكل ملف المبيعات (منتج، شهر، كمية) بلا عمود عميل — لا يُقبَل
    صامتاً كملف عميل بعميل واحد ضمني."""
    data = csv("Product,Month,Quantity\nPump,Jan 2024,10\nPump,Feb 2024,20\n")

    with pytest.raises(DataValidationError) as excinfo:
        parse_customer_upload(data, "no_customer.csv")

    assert excinfo.value.context["code"] == "no_customer_columns"


def test_customer_mapping_rescues_an_unrecognised_file():
    data = csv(
        "Material,Sold-To,Zeitraum,Betrag\n"
        "PUMP-01,ACME,2024-01,10\nPUMP-01,ACME,2024-02,12\n"
    )

    dataset = parse_customer_upload_with_mapping(
        data, "sap.csv",
        product_column="Material", customer_column="Sold-To",
        month_column="Zeitraum", quantity_column="Betrag",
    )

    assert dataset.rows == {"ACME": {"PUMP-01": [10.0, 12.0]}}


def test_customer_mapping_rejects_reusing_the_same_column_twice():
    with pytest.raises(DataValidationError) as excinfo:
        parse_customer_upload_with_mapping(
            CUSTOMER_CSV, "customers.csv",
            product_column="Product", customer_column="Product",
            month_column="Month", quantity_column="Quantity",
        )

    assert excinfo.value.context["code"] == "duplicate_mapped_columns"


def test_duplicate_product_customer_month_rows_are_summed_and_warned():
    data = csv(
        "Product,Customer,Month,Quantity\n"
        "Pump,ACME,Jan 2024,30\nPump,ACME,Jan 2024,20\nPump,ACME,Feb 2024,10\n"
    )

    dataset = parse_customer_upload(data, "dup.csv")

    assert dataset.rows == {"ACME": {"Pump": [50.0, 10.0]}}
    assert any(w.code == "customer_duplicate_rows" for w in dataset.warnings)


def test_customer_negative_quantities_are_clipped_to_zero():
    data = csv("Product,Customer,Month,Quantity\nPump,ACME,Jan 2024,-5\nPump,ACME,Feb 2024,5\n")

    dataset = parse_customer_upload(data, "negative.csv")

    assert dataset.rows == {"ACME": {"Pump": [0.0, 5.0]}}
    assert any(w.code == "negatives" for w in dataset.warnings)


def test_customer_template_has_the_four_expected_columns():
    import io

    import pandas as pd

    frame = pd.read_csv(io.BytesIO(customer_csv_template()), encoding="utf-8-sig")

    assert list(frame.columns) == ["المنتج", "العميل", "الشهر", "الكمية"]
