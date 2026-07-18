# tests/test_i18n.py
"""
اختبارات الترجمة.

الاختبار الأهم هنا هو `test_every_string_has_both_languages`: لغتان
تعنيان أن كل نص جديد يحتاج صياغتين، والنسيان حتمي. هذا الاختبار يجعل
النسيان يفشل البناء بدل أن يُكتشَف حين يرى مستخدم إنجليزي نصاً عربياً.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from ui import i18n
from ui.i18n import LANGUAGES, STRINGS

UI_FILES = [
    Path("app.py"),
    Path("ui/data_source.py"),
    Path("ui/sidebar.py"),
    Path("ui/dashboard.py"),
    Path("ui/export.py"),
    *sorted(Path("ui/pages").glob("*.py")),
]


# ---------------------------------------------------------------------------
# اكتمال القاموس
# ---------------------------------------------------------------------------
def test_every_string_has_both_languages():
    """نص بلغة واحدة = مستخدم يرى لغة لا يقرأها وسط واجهته."""
    missing = [
        f"{key}[{code}]"
        for key, entry in STRINGS.items()
        for code in LANGUAGES
        if not entry.get(code)
    ]

    assert missing == [], f"ترجمات ناقصة: {missing}"


def test_no_key_is_orphaned():
    """مفتاح لا يستدعيه أحد نصٌّ يُترجَم مرّتين ولا يُقرأ مرة.

    وأخطر منه أنه يُخفي عطلاً: "app.title" كان هنا مترجماً بالكامل ولا
    يستدعيه أحد، بينما app.py يمرّر PAGE_TITLE — نصاً عربياً مثبَّتاً في
    config.py. فكان الزائر يبدّل إلى الإنجليزية، وتُترجم الصفحة كلها، ويبقى
    تبويب متصفّحه عربياً. المفتاح اليتيم كان الدليل، ولم يكن أحد يقرؤه.

    المفاتيح الديناميكية (f"rec.{code}") تُستثنى بالبادئة: لا يظهر اسمها
    الكامل في الكود أبداً.

    نطاقا البحث مختلفان عمداً. الحرفيّ يستثني ui/i18n.py وإلا طابق كل مفتاح
    تعريفَه في STRINGS فلم يُكتشف يتيم قط. والديناميكيّ يشمله: format_reason
    و format_recommendation تعيشان هناك، وهما تبنيان "reason.*" و"rec.*".
    """
    everywhere = [
        path
        for path in Path(".").rglob("*.py")
        if ".venv" not in str(path) and "__pycache__" not in str(path)
    ]
    dynamic_sources = "\n".join(p.read_text(encoding="utf-8") for p in everywhere)
    literal_sources = "\n".join(
        p.read_text(encoding="utf-8") for p in everywhere if p != Path("ui/i18n.py")
    )

    orphans = []
    for key in STRINGS:
        if f'"{key}"' in literal_sources or f"'{key}'" in literal_sources:
            continue
        prefix = key.split(".")[0]
        if re.search(rf'f["\']{re.escape(prefix)}\.\{{', dynamic_sources):
            continue  # يُبنى ديناميكياً
        orphans.append(key)

    assert orphans == [], f"مفاتيح لا يستدعيها أحد: {orphans}"


def test_the_browser_tab_title_is_translated():
    """العنوان يتبع الرابط، ولا يعود نصاً مثبَّتاً بلغة واحدة."""
    assert i18n.STRINGS["app.title"]["ar"] != i18n.STRINGS["app.title"]["en"]

    source = Path("app.py").read_text(encoding="utf-8")
    assert "page_title=page_title()" in source, "app.py لا يستعمل العنوان المترجَم"
    assert "PAGE_TITLE" not in source.replace(
        "# لا PAGE_TITLE من config.py", ""
    ), "app.py عاد إلى عنوان مثبَّت"


def test_placeholders_match_across_languages():
    """`{count}` في العربية و`{n}` في الإنجليزية = KeyError وقت العرض،
    على مستخدم واحد فقط ولغة واحدة فقط — أسوأ أنواع الأعطال."""
    mismatched = []
    for key, entry in STRINGS.items():
        sets = {
            code: set(re.findall(r"\{(\w+)", text))
            for code, text in entry.items()
        }
        if len(set(map(frozenset, sets.values()))) > 1:
            mismatched.append(f"{key}: {sets}")

    assert mismatched == [], f"متغيّرات غير متطابقة: {mismatched}"


def test_no_key_is_empty():
    assert all(key.strip() for key in STRINGS)


# ---------------------------------------------------------------------------
# لا نصوص حرفية في الواجهة
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", UI_FILES, ids=lambda p: p.name)
def test_no_hardcoded_arabic_in_widget_calls(path: Path):
    """نص عربي حرفي داخل استدعاء Streamlit = نص لن يُترجَم أبداً.

    يفحص الوسيط الأول للـ widgets ووسائط العرض الشائعة. التعليقات
    و docstrings عربية بالكامل عمداً — هي للمطوّر لا للمستخدم.
    """
    source = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r'(?:st\.\w+\(|columns\[\d\]\.\w+\(|help=|title=|text=|name=|label=)'
        r'\s*"([^"]*[ء-ي][^"]*)"'
    )
    offenders = pattern.findall(source)

    assert offenders == [], f"نصوص غير مترجَمة في {path}: {offenders[:4]}"


# ---------------------------------------------------------------------------
# t()
# ---------------------------------------------------------------------------
def test_a_missing_key_is_loud_not_silent():
    """⟨key⟩ قبيح عمداً: نص مفقود يعود بالعربية لمستخدم إنجليزي يبدو
    عطلاً عشوائياً، بينما ⟨exec.title⟩ يقول ما نقص وأين."""
    assert i18n.t("no.such.key") == "⟨no.such.key⟩"


def test_english_is_the_default(monkeypatch):
    """الأداة مجانية وجمهورها عالمي؛ العربية على بُعد نقرة."""
    monkeypatch.setattr(i18n.st, "session_state", {})

    assert i18n.current_language() == "en"


def test_parameters_are_interpolated(monkeypatch):
    monkeypatch.setattr(i18n.st, "session_state", {"language": "en"})

    assert "5" in i18n.t("warn.negatives", count=5)


def test_arabic_is_served_when_selected(monkeypatch):
    monkeypatch.setattr(i18n.st, "session_state", {"language": "ar"})

    assert i18n.t("nav.executive") == "النظرة التنفيذية"


def test_rtl_follows_the_language(monkeypatch):
    monkeypatch.setattr(i18n.st, "session_state", {"language": "ar"})
    assert i18n.is_rtl()

    monkeypatch.setattr(i18n.st, "session_state", {"language": "en"})
    assert not i18n.is_rtl()


# ---------------------------------------------------------------------------
# أسماء الأشهر
# ---------------------------------------------------------------------------
def test_arabic_demo_months_are_shown_in_english(monkeypatch):
    """بيانات العرض بأشهر عربية؛ عرضها في واجهة إنجليزية يبدو عطلاً."""
    monkeypatch.setattr(i18n.st, "session_state", {"language": "en"})

    assert i18n.format_month("ديسمبر 2022") == "December 2022"


def test_english_months_are_shown_in_arabic(monkeypatch):
    monkeypatch.setattr(i18n.st, "session_state", {"language": "ar"})

    assert i18n.format_month("Jan 2024") == "يناير 2024"


def test_unrecognised_labels_are_left_alone(monkeypatch):
    """تسمية مخصّصة من ملف المستخدم ليست خطأً يُصحَّح — هي بياناته."""
    monkeypatch.setattr(i18n.st, "session_state", {"language": "en"})

    assert i18n.format_month("W1-2024") == "W1-2024"


def test_formatting_a_list_preserves_order(monkeypatch):
    monkeypatch.setattr(i18n.st, "session_state", {"language": "en"})

    assert i18n.format_months(["ديسمبر 2022", "يناير 2023"]) == [
        "December 2022", "January 2023",
    ]


# ---------------------------------------------------------------------------
# رسائل الأخطاء
# ---------------------------------------------------------------------------
def test_an_exception_code_is_translated(monkeypatch):
    """رسالة "لم يُفهَم أي عمود كشهر" قيمة لا ضجيج — ومستخدم إنجليزي
    يستحقها بلغته."""
    monkeypatch.setattr(i18n.st, "session_state", {"language": "en"})
    from core.exceptions import DataValidationError

    exc = DataValidationError("عربي للسجل", context={"code": "empty_file"})

    assert i18n.error(exc) == "The file is empty."


def test_an_exception_without_a_code_falls_back_to_its_message(monkeypatch):
    monkeypatch.setattr(i18n.st, "session_state", {"language": "en"})
    from core.exceptions import AppError

    exc = AppError("raw detail")

    assert i18n.error(exc) == "raw detail"


def test_an_unknown_code_falls_back_rather_than_showing_a_marker(monkeypatch):
    monkeypatch.setattr(i18n.st, "session_state", {"language": "en"})
    from core.exceptions import AppError

    exc = AppError("raw detail", context={"code": "not_in_catalogue"})

    assert i18n.error(exc) == "raw detail"


def test_a_code_with_missing_params_falls_back_instead_of_crashing(monkeypatch):
    """سياق ناقص يجب ألا يُسقط الصفحة — الرسالة الأصلية أفضل من انهيار."""
    monkeypatch.setattr(i18n.st, "session_state", {"language": "en"})
    from core.exceptions import DataValidationError

    exc = DataValidationError("fallback", context={"code": "too_few_months"})

    assert i18n.error(exc) == "fallback"


# ---------------------------------------------------------------------------
# كل رمز خطأ/تحذير من الخدمات له مفتاح
# ---------------------------------------------------------------------------
def test_every_ingest_error_code_has_a_translation():
    source = Path("services/ingest.py").read_text(encoding="utf-8")
    codes = set(re.findall(r'"code":\s*"(\w+)"', source))

    missing = [code for code in codes if f"error.{code}" not in STRINGS]
    assert missing == [], f"رموز أخطاء بلا ترجمة: {missing}"


def test_every_ingest_warning_code_has_a_translation():
    source = Path("services/ingest.py").read_text(encoding="utf-8")
    codes = set(re.findall(r'Warning_\("(\w+)"', source))

    missing = [code for code in codes if f"warn.{code}" not in STRINGS]
    assert missing == [], f"رموز تحذيرات بلا ترجمة: {missing}"


def test_every_demand_class_has_a_label_and_help():
    from services.forecast_engine.intermittent import DemandClass

    for demand_class in DemandClass:
        assert f"class.{demand_class.value}" in STRINGS
        assert f"class.{demand_class.value}.help" in STRINGS


def test_every_risk_factor_has_a_label():
    from services.risk_service import FACTOR_WEIGHTS

    for name in FACTOR_WEIGHTS:
        assert f"factor.{name}" in STRINGS


# ---------------------------------------------------------------------------
# بقاء اللغة — انحدار كشفه التشغيل الحقيقي
# ---------------------------------------------------------------------------
class _FakeQueryParams(dict):
    """بديل st.query_params في الاختبارات (لا جلسة Streamlit حيّة)."""


def test_the_url_seeds_the_language_on_first_load(monkeypatch):
    """انحدار: session_state لا ينجو من إعادة تحميل الصفحة.

    قياس فعلي قبل الإصلاح: التبديل للعربية يثبت عبر روابط التنقّل (لا
    تُعيد التحميل)، لكن F5 أو فتح رابط محفوظ كان يعيد الإنجليزية —
    فيضطر المستخدم لإعادة الاختيار في كل زيارة. ?lang=ar يحلّها ويجعل
    اللغة قابلة للمشاركة أيضاً.
    """
    monkeypatch.setattr(i18n.st, "session_state", {})
    monkeypatch.setattr(i18n.st, "query_params", _FakeQueryParams(lang="ar"))

    assert i18n.current_language() == "ar"


def test_the_url_only_seeds_the_first_load(monkeypatch):
    """اختيار المستخدم داخل الجلسة يعلو على الرابط."""
    monkeypatch.setattr(i18n.st, "session_state", {"language": "en"})
    monkeypatch.setattr(i18n.st, "query_params", _FakeQueryParams(lang="ar"))

    assert i18n.current_language() == "en"


def test_an_invalid_url_language_is_ignored(monkeypatch):
    """?lang=zz لا يُفعّل لغة غير موجودة ولا يُسقط الصفحة."""
    monkeypatch.setattr(i18n.st, "session_state", {})
    monkeypatch.setattr(i18n.st, "query_params", _FakeQueryParams(lang="zz"))

    assert i18n.current_language() == "en"


def test_a_missing_query_param_falls_back_to_the_default(monkeypatch):
    monkeypatch.setattr(i18n.st, "session_state", {})
    monkeypatch.setattr(i18n.st, "query_params", _FakeQueryParams())

    assert i18n.current_language() == "en"


def test_the_too_few_months_message_translates_its_own_unit(monkeypatch):
    """رسالة "قلّة الفترات" تحمل رمز الحبيبة الخام ("weekly") من الخدمة،
    وتحتاجه مصرَّفاً — نفس آلية unsupported_granularity السابقة، لكن على
    الرسالة التي تصل فعلاً الآن (بعد بند 1 في ROADMAP، كل الحبيبات مقبولة
    وunsupported_granularity لم يعد يُرفَع أصلاً).

    القيمة تُترجَم عبر t() متداخل، واسم المتغيّر واحد في الصياغتين — وإلا
    انكسر شرط تطابق المتغيّرات، وهو يحرس من صياغة تنهار للغة واحدة فقط.
    """
    from core.exceptions import DataValidationError

    exc = DataValidationError(
        "raw",
        context={
            "code": "too_few_months", "months": 1, "minimum": 2,
            "granularity": "weekly",
        },
    )

    monkeypatch.setattr(i18n.st, "session_state", {"language": "en"})
    english = i18n.error(exc)
    assert "weeks" in english

    monkeypatch.setattr(i18n.st, "session_state", {"language": "ar"})
    arabic = i18n.error(exc)
    assert "أسبوعاً" in arabic


def test_every_granularity_bucket_has_a_label_and_unit():
    from services.ingest import GRANULARITY_BUCKETS

    for name in GRANULARITY_BUCKETS.values():
        assert f"granularity.{name}" in STRINGS
        assert f"granularity.unit.{name}" in STRINGS
