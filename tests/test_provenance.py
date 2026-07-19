# tests/test_provenance.py
"""
سجلّ التدقيق — الورقة التي تُرافق ملفاً يُبنى عليه أمر شراء.

ما يُختبَر هنا ليس التنسيق بل **ما يصمد في نزاع**: أن تصل البصمة
والتاريخ والمصدر، وأن يُفرَّق بين "لم يُقَس" و"صفر"، وأن يُقرأ الملف
كما كُتب حين يفتحه محلّل بأداته لا بعينه.
"""
from __future__ import annotations

import io

import pandas as pd

from services.provenance import RunProvenance, fingerprint

PRODUCTS = {"A": [1.0, 2.0, 3.0], "B": [4.0, 5.0, 6.0]}


def _rows(provenance) -> dict[str, str]:
    return dict(provenance.rows())


# ---------------------------------------------------------------------------
# البصمة — ما يحسم «أي ملف بُني عليه هذا؟»
# ---------------------------------------------------------------------------
def test_the_fingerprint_changes_when_a_number_changes():
    """أكثر النزاعات وقوعاً حول *البيانات* لا النموذج: تصديرة صُحّحت
    ونُسي إعادة الحساب. بصمةٌ لا تتغيّر بتغيّر رقم لا تحسم شيئاً."""
    assert fingerprint(PRODUCTS) != fingerprint({**PRODUCTS, "A": [1.0, 2.0, 99.0]})


def test_the_fingerprint_is_stable_across_runs():
    """بصمة تتبدّل بلا سبب تُبطل السجلّ كلّه."""
    assert fingerprint(PRODUCTS) == fingerprint(dict(reversed(list(PRODUCTS.items()))))


def test_the_fingerprint_notices_a_renamed_product():
    assert fingerprint(PRODUCTS) != fingerprint({"A": [1.0, 2.0, 3.0], "C": [4.0, 5.0, 6.0]})


# ---------------------------------------------------------------------------
# الصدق: «لم يُقَس» ليست «صفر»
# ---------------------------------------------------------------------------
def test_unmeasured_accuracy_is_a_dash_not_a_zero():
    """الفرق هو كل شيء في نزاع: "—" تعني أن المستخدم لم يشغّل التحقّق،
    و"0%" تعني أنه شغّله فكانت النتيجة صفراً. خلطهما يقلب الوقائع."""
    rows = _rows(RunProvenance(products=PRODUCTS, granularity="monthly", period_count=3))

    assert rows["audit.median_wape"] == "—"
    assert rows["audit.beat_naive"] == "—"
    assert rows["audit.measured_share"] == "—"


def test_measured_accuracy_is_recorded_when_it_exists():
    rows = _rows(RunProvenance(
        products=PRODUCTS, granularity="monthly", period_count=3,
        measured_share=0.42, median_wape=58.0, beat_naive_share=0.63,
    ))

    assert rows["audit.measured_share"] == "42%"
    assert rows["audit.median_wape"] == "58%"
    assert rows["audit.beat_naive"] == "63%"


def test_the_warnings_the_user_saw_are_not_forgotten_after_the_screen_closes():
    rows = _rows(RunProvenance(
        products=PRODUCTS, granularity="monthly", period_count=3,
        warning_codes=["non_numeric", "total_rows"],
    ))

    assert "non_numeric" in rows["audit.warnings"]
    assert "total_rows" in rows["audit.warnings"]


def test_the_sheet_states_what_it_does_not_prove():
    """ادّعاءٌ ضمنيّ بأن الورقة "تُثبت صحّة التنبؤ" أسوأ من غيابها."""
    assert "audit.note" in _rows(
        RunProvenance(products=PRODUCTS, granularity="monthly", period_count=3)
    )


# ---------------------------------------------------------------------------
# ما يصل إلى الملف فعلاً — لا ما تُرجعه الدالة
# ---------------------------------------------------------------------------
def _sheet(provenance) -> pd.DataFrame:
    from ui.export import write_audit_sheet

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        write_audit_sheet(writer, provenance)
    return pd.read_excel(io.BytesIO(buffer.getvalue()))


def test_no_value_reads_back_as_empty_when_the_sheet_is_loaded():
    """⚠️ عطل حقيقي وجده أول ملف وُلِّد: كانت "لا تحذيرات" تُكتب "None"
    بالإنجليزية — وهي ضمن قيم pandas الفارغة الافتراضية، فتُقرأ NaN.

    أي أن السطر يصل **فارغاً** لمن يحمّل الورقة بأداة تحليل، وهو عكس ما
    يقوله بالضبط. سجلٌّ يُقرأ خطأً أسوأ من غيابه.
    """
    frame = _sheet(RunProvenance(
        products=PRODUCTS, granularity="monthly", period_count=3, warning_codes=[],
    ))

    assert not frame.isna().any().any(), (
        f"قيمة تُقرأ فارغة:\n{frame[frame.isna().any(axis=1)]}"
    )


def test_the_exported_sheet_carries_the_source_and_the_fingerprint():
    frame = _sheet(RunProvenance(
        products=PRODUCTS, granularity="monthly", period_count=3,
        source_name="factory_export.xlsx",
    ))
    values = frame.iloc[:, 1].astype(str).tolist()

    assert "factory_export.xlsx" in values
    assert fingerprint(PRODUCTS) in values


def test_the_audit_sheet_comes_first_in_the_purchase_plan_file():
    """Excel يفتح على الورقة الأولى، ومن يفتح الملف في نزاع يبحث عن
    "متى؟" و"أي ملف؟" قبل أي شيء."""
    from ui.pages.purchase_plan import _excel_bytes

    blob = _excel_bytes([], [], [], RunProvenance(
        products=PRODUCTS, granularity="monthly", period_count=3,
    ))

    assert pd.ExcelFile(io.BytesIO(blob)).sheet_names[0] == "Audit trail"


def test_a_file_exported_without_provenance_still_works():
    """السجلّ إضافة لا شرط — تصديرٌ بلا سياق يجب ألا ينهار."""
    from ui.pages.purchase_plan import _excel_bytes

    assert _excel_bytes([], [], [])


# ---------------------------------------------------------------------------
# التصاق تقرير التحقّق — دقّة ملفٍ لا تُختم على سجلّ ملفٍ آخر
# ---------------------------------------------------------------------------
def _with_session(state):
    from unittest.mock import patch

    import ui.pages.executive as executive

    return patch.object(executive.st, "session_state", state)


def test_a_validation_report_does_not_survive_a_file_swap():
    """⚠️ عطل أثبته التشغيل: تحقّقٌ على ملف شهري بقي في الجلسة بعد رفع
    ملف ربعي، فخُتم سجلّ تدقيق الربعي ببصمته هو ودقّةِ الشهري — وثيقةُ
    النزاعات نفسها تكذب."""
    from ui.pages.executive import store_validation_report, stored_validation_report

    file_a = {"A": [1.0, 2.0, 3.0]}
    file_b = {"A": [9.0, 9.0, 9.0]}
    state = {}
    with _with_session(state):
        store_validation_report("report-of-A", file_a)

        assert stored_validation_report(file_a) == "report-of-A"
        assert stored_validation_report(file_b) is None


def test_the_purchase_plan_provenance_refuses_another_files_accuracy():
    from unittest.mock import patch

    import ui.pages.purchase_plan as pp
    from ui.pages.executive import store_validation_report

    file_a = {"A": [1.0, 2.0, 3.0]}
    file_b = {"A": [9.0, 9.0, 9.0]}
    state = {}
    with _with_session(state), patch.object(pp.st, "session_state", state):
        store_validation_report("report-of-A", file_a)
        plan = type("P", (), {"lines": []})()
        provenance = pp._provenance(
            file_b, ["Jan 2024"], "monthly", plan, 6, 0, False, None,
        )

    assert dict(provenance.rows())["audit.median_wape"] == "—"


def test_the_downloaded_file_describes_the_plan_not_the_screen():
    """الباب الثاني لنفس العطل: الخطة تبقى بعد تبديل الملف (بتحذير)،
    وزرّ التنزيل يبقى فعّالاً. السجلّ يُلتقط لحظة الحساب ويُخزَّن مع
    الخطة — فما يُنزَّل يصف ما حُسب، لا ما على الشاشة الآن."""
    import inspect

    import ui.pages.purchase_plan as pp

    source = inspect.getsource(pp.render)
    assert "st.session_state.get(PROVENANCE_KEY)" in source, (
        "التنزيل يجب أن يقرأ السجلّ المخزَّن، لا أن يبنيه من بيانات الشاشة"
    )
    compute_block = source[:source.index("st.download_button")]
    assert "PROVENANCE_KEY] = _provenance(" in compute_block.replace("\n", "").replace(" ", "") \
        or "st.session_state[PROVENANCE_KEY]" in compute_block, (
        "السجلّ يجب أن يُلتقط في كتلة الحساب"
    )
