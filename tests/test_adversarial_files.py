# tests/test_adversarial_files.py
"""
حزمة الملفات العدائية — ما تُخرجه أنظمة ERP فعلياً، لا ما نتمنّاه.

## لماذا وُجد هذا الملف

عطل فواصل الآلاف ("1,200" تُقرأ صفراً) نجا من **611 اختباراً** ومن خمسة
ملفات حقيقية ومن ثلاث جولات فحص يدوي. كشفه أوّل ملفٍ اصطناعي لم يُصنَع
من كتالوجنا.

السبب بنيوي: كل اختباراتنا وكل ملفاتنا تفترض **أرقاماً نظيفة وبنيةً
مرتّبة**. تصديرة ERP حقيقية لا تفترض ذلك — فيها رموز عملات، ووحدات
ملحقة، وصفوف إجماليات، وأسماء مكرّرة، وعلامات اتجاه غير مرئية.

فكل حالة هنا تمثّل شكلاً رأيناه أو نتوقّعه في تصديرة حقيقية، ومصنَّفة
بما **يجب** أن يحدث لا بما يحدث:

  - **تُقرأ**: بيانات سليمة مموّهة — يجب أن تصل كاملةً.
  - **تُرفَض بصوت**: غامضة فعلاً — الرفض الصريح أأمن من التخمين.
  - **تُصحَّح بتحذير**: بنية معطوبة قابلة للإنقاذ — تُصلَح ويُقال ذلك.

⚠️ القاعدة الحاكمة: **لا صفر صامت**. رقمٌ حقيقي يصير صفراً بلا ذكرٍ
يجعل منتجاً قائماً يبدو متوقّفاً، فتوصي الأداة بإنتاج صفر منه — وهي
التوصية التي يُبنى عليها أمر شراء.
"""
from __future__ import annotations

import io

import pandas as pd
import pytest

from services.ingest import parse_upload

MONTHS = ["Jan 2024", "Feb 2024", "Mar 2024", "Apr 2024"]
CLEAN = [1200.0, 1100.0, 950.0, 900.0]


def _upload(frame: pd.DataFrame):
    buffer = io.BytesIO()
    frame.to_excel(buffer, index=False)
    return parse_upload(buffer.getvalue(), "export.xlsx")


def _one_product(cells: list, months: list[str] = MONTHS) -> pd.DataFrame:
    return pd.DataFrame({"Product": ["A"], **{m: [cells[i]] for i, m in enumerate(months)}})


def _codes(dataset) -> set[str]:
    return {w.code for w in dataset.warnings}


# ---------------------------------------------------------------------------
# تُقرأ: أرقام حقيقية مموّهة — الصفر هنا فقدُ بيانات
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cells,label", [
    (["1,200", "1,100", "950", "900"], "فواصل آلاف"),
    (["$1,200", "$1,100", "$950", "$900"], "رمز عملة"),
    (["1200 ر.س", "1100 ر.س", "950 ر.س", "900 ر.س"], "عملة لاحقة"),
    (["1,200 kg", "1,100 kg", "950 kg", "900 kg"], "وحدة ملحقة"),
    (["'1200", "'1100", "'950", "'900"], "فاصلة Excel العليا"),
    (["1 200", "1 100", "950", "900"], "فراغ يفصل الآلاف"),
    (["  1200  ", " 1100 ", "950", "900"], "فراغ محيط"),
    (["1.2E3", "1.1E3", "950", "900"], "ترميز أسّي"),
    (["١٢٠٠", "١١٠٠", "٩٥٠", "٩٠٠"], "أرقام عربية-هندية"),
])
def test_a_disguised_number_arrives_intact(cells, label):
    """كل صفّ هنا كان أو كاد يُقرأ صفراً. القيمة تصل كاملة، بلا تحذير —
    قراءةٌ سليمة لا يجوز أن تُقلق المستخدم."""
    dataset = _upload(_one_product(cells))

    assert dataset.products["A"] == CLEAN, f"فقدُ بيانات في: {label}"
    assert "non_numeric" not in _codes(dataset), f"تحذير زائف في: {label}"


def test_an_accounting_negative_is_a_return_not_an_unreadable_cell():
    """(500) تعني -500 في كل تصديرة مالية. كانت تُقرأ "غير رقمية" فتصير
    صفراً — أي أن مرتجعاً يُمحى بدل أن يُحذَّر منه. الآن تُقصّ إلى صفر
    كبقية السوالب، لكن **بتحذير يسمّي السبب**."""
    dataset = _upload(_one_product(["(500)", "1100", "950", "900"]))

    assert "negatives" in _codes(dataset)
    assert "non_numeric" not in _codes(dataset)


# ---------------------------------------------------------------------------
# تُرفَض بصوت: غامضة فعلاً — التخمين أخطر من الرفض
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cells,why", [
    (["1200,5", "1100,5", "950", "900"], "فاصلة عشرية أوروبية: 1,20 تعني 1.20 هناك ولا شيء هنا"),
    (["2 x 500", "1100", "950", "900"], "رقمان في خلية: طرح غير الرقمي يُنتج 2500 المخترَع"),
    (["abc", "1100", "950", "900"], "نصّ محض"),
])
def test_a_genuinely_ambiguous_cell_is_refused_loudly(cells, why):
    """يصير صفراً — لكن **بتحذير يسمّي المنتج**، فيعرف المستخدم أين ينظر.
    الصمت هنا هو العطل، لا الصفر."""
    dataset = _upload(_one_product(cells))

    assert "non_numeric" in _codes(dataset), why
    warning = next(w for w in dataset.warnings if w.code == "non_numeric")
    assert "A" in warning.params["products"]


# ---------------------------------------------------------------------------
# تُصحَّح بتحذير: بنية معطوبة قابلة للإنقاذ
# ---------------------------------------------------------------------------
def test_a_totals_row_is_not_ingested_as_a_product():
    """صف "Total" مجموعُ منتجات لا منتج. أثره مضاعَف: يضخّم عدد المنتجات،
    وحجمه = مجموع الكتالوج فيتصدّر **كل** شاشة مرتّبة بالحجم — وهي كل
    الشاشات بعد إصلاح الترتيب."""
    frame = pd.DataFrame({
        "Product": ["A", "B", "Total"],
        **{m: [1, 5, 6] for m in MONTHS},
    })

    dataset = _upload(frame)

    assert set(dataset.products) == {"A", "B"}
    assert "total_rows" in _codes(dataset)


@pytest.mark.parametrize("name", ["Total", "TOTAL", "Grand Total", "المجموع", "الإجمالي"])
def test_totals_rows_are_recognised_in_both_languages(name):
    frame = pd.DataFrame({"Product": ["A", name], **{m: [1, 1] for m in MONTHS}})

    assert set(_upload(frame).products) == {"A"}


def test_a_repeated_product_name_is_summed_not_overwritten():
    """صفّان لنفس المنتج = مستودعان أو خطّا إنتاج، لا خطأ إدخال — نفس قرار
    ملف المخزون. كان الصفّ الثاني **يمحو الأول بصمت** لأن الإسناد إلى
    dict لا يجمع: نصف مبيعات المنتج تختفي بلا أثر."""
    frame = pd.DataFrame({"Product": ["A", "A"], **{m: [10, 5] for m in MONTHS}})

    dataset = _upload(frame)

    assert dataset.products["A"] == [15.0] * 4
    assert "merged_rows" in _codes(dataset)


def test_invisible_direction_marks_do_not_split_one_product_into_two():
    """علامات RTL تنجو من تصديرات الواجهات العربية وهي غير مرئية. أثرها
    ليس تجميلياً: الربط بين ملف المبيعات وملف المخزون **بالاسم**، فعلامة
    خفية في أحدهما تعني منتجاً بلا مخزون ومخزوناً بلا منتج — وكلاهما يبدو
    سليماً على الشاشة."""
    frame = pd.DataFrame({
        "Product": ["‏منتج أ‎", "منتج أ"],
        **{m: [10, 5] for m in MONTHS},
    })

    dataset = _upload(frame)

    assert list(dataset.products) == ["منتج أ"]
    assert dataset.products["منتج أ"] == [15.0] * 4


def test_a_blank_row_in_the_middle_is_skipped_not_read_as_a_product():
    frame = pd.DataFrame({
        "Product": ["A", None, "B"],
        **{m: [1, None, 2] for m in MONTHS},
    })

    assert set(_upload(frame).products) == {"A", "B"}


# ---------------------------------------------------------------------------
# صيغ التواريخ — ملف مرفوض عند الباب هو صفقة ضائعة
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("labels,why", [
    (["Jan-24", "Feb-24", "Mar-24", "Apr-24"], "سنة من رقمين — شكل Excel شائع"),
    (["202401", "202402", "202403", "202404"], "YYYYMM ملتصقة — مخرج SAP"),
    (["Jan 2024", "2024-02", "مارس 2024", "Apr-2024"], "صيغ مختلطة في ملف واحد"),
])
def test_common_erp_date_shapes_are_read(labels, why):
    dataset = _upload(_one_product([1, 2, 3, 4], labels))

    assert dataset.product_count == 1, why
    assert len(dataset.months) == 4


def test_a_two_digit_year_is_a_year_not_a_day():
    """⚠️ pandas تقرأ "Jan-24" أحياناً اليومَ 24 من يناير في السنة الحالية —
    رقم يبدو سليماً وهو خطأ سنة كاملة. لذا تُجرَّب صيغتنا قبلها."""
    from services.ingest import parse_full_date

    assert parse_full_date("Jan-24").year == 2024
    assert parse_full_date("Jan-24").day == 1
