# ui/i18n.py
"""
الترجمة: العربية والإنجليزية.

كل نص يراه المستخدم يمرّ من هنا. القاعدة: لا نص حرفي في ملفات الواجهة —
وإلا نسي أحدهم ترجمته وظهرت عربية وسط إنجليزية.

## رسائل الأخطاء

الخدمات ترفع استثناءات برسائل عربية — وهي *للسجلات* (طبقة تقنية، لا
تُترجَم). لكن بعضها يصل المستخدم، وأهمّها أخطاء رفع الملفات: رسالة
"لم يُفهَم أي عمود كشهر" هي *قيمة* لا ضجيج، ومستخدم إنجليزي يستحقها.

الحل: الاستثناء يحمل `code` في سياقه، والواجهة تترجمه عبر `error()`.
الرسالة الأصلية تبقى للسجل وكاحتياط إن نقص المفتاح.

## أسماء الأشهر

بيانات العرض بأشهر عربية ("ديسمبر 2022"). عرضها في واجهة إنجليزية يبدو
عطلاً. `format_month` يحلّلها إلى تاريخ ويعيد صياغتها باللغة الحالية —
ويترك ما لا يفهمه كما هو بدل تشويهه.
"""
from __future__ import annotations

import re
from typing import Any

import streamlit as st

LANGUAGES = {"ar": "العربية", "en": "English"}
DEFAULT_LANGUAGE = "en"  # الأداة مجانية وجمهورها عالمي؛ العربية بنقرة
SESSION_KEY = "language"

ENGLISH_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
ARABIC_MONTHS = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
]

# أشكال "الشهر المجرّد" التي وحدها تُترجَم (راجع _is_bare_month_label):
# اسم شهر إنجليزي (كامل أو مختصر) + سنة، أو YYYY-MM. لا يوم فيها — "01 Jan
# 2023" اليومية تحمل يوماً فلا تُطابِق، فتبقى كما هي بلا طمس.
_BARE_MONTH_NAME = re.compile(
    r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{4}$",
    re.IGNORECASE,
)
_ISO_YEAR_MONTH = re.compile(r"^\d{4}[-/]\d{1,2}$")
_JUST_A_YEAR = re.compile(r"\d{4}")


QUERY_PARAM = "lang"


def _language_from_url() -> str | None:
    """اللغة من الرابط (?lang=ar).

    st.query_params يحتاج جلسة Streamlit حيّة؛ في الاختبارات لا توجد.
    """
    try:
        raw = st.query_params.get(QUERY_PARAM, "")
    except Exception:  # noqa: BLE001
        return None
    return raw if raw in LANGUAGES else None


def current_language() -> str:
    """لغة الجلسة.

    الرابط هو المصدر عند أول تحميل، ثم session_state.

    لماذا الرابط وليس session_state وحده: session_state لا ينجو من إعادة
    تحميل الصفحة — قياس فعلي: التبديل للعربية يثبت عبر روابط التنقّل
    (لا تُعيد التحميل)، لكن F5 أو فتح رابط محفوظ كان يعيد الإنجليزية.
    ?lang=ar يجعل اللغة قابلة للحفظ وللمشاركة أيضاً.
    """
    if SESSION_KEY not in st.session_state:
        st.session_state[SESSION_KEY] = _language_from_url() or DEFAULT_LANGUAGE
    return st.session_state[SESSION_KEY]


def is_rtl() -> bool:
    return current_language() == "ar"


def page_title() -> str:
    """عنوان تبويب المتصفّح — بلغة الزائر.

    منفصلة عن t("app.title") لسبب تقني: st.set_page_config يجب أن يسبق كل
    أمر Streamlit آخر، بينما current_language() تكتب في st.session_state.
    فنقرأ الرابط وحده هنا (مسموح قبل set_page_config — قِيس)، ونقبل
    الافتراضي عند غيابه.

    الثمن مقبول: الزائر الذي بدّل لغته يحمل ?lang في رابطه (المبدّل يكتبه)،
    فيتبعه التبويب. ومن لم يبدّل يرى الافتراضي — وهو ما كان يريده.

    ولماذا وُجدت أصلاً: كان app.py يمرّر PAGE_TITLE من config.py — نصاً
    عربياً مثبَّتاً. فيبدّل الزائر إلى الإنجليزية، وتُترجم الصفحة كلها،
    ويبقى تبويب متصفّحه عربياً. المفتاح المترجَم كان موجوداً في هذا القاموس
    منذ البداية ولا يستدعيه أحد.
    """
    return STRINGS["app.title"][_language_from_url() or DEFAULT_LANGUAGE]


def t(key: str, **kwargs: Any) -> str:
    """نص مترجَم. مفتاح مفقود يظهر كـ ⟨key⟩ — صاخب عمداً ليُلاحَظ.

    الصمت هنا أسوأ من القبح: نص إنجليزي مفقود يظهر بالعربية لمستخدم
    إنجليزي فيبدو عطلاً عشوائياً، بينما ⟨executive.title⟩ يقول ما نقص.
    """
    entry = STRINGS.get(key)
    if entry is None:
        return f"⟨{key}⟩"
    text = entry.get(current_language()) or entry.get("en") or f"⟨{key}⟩"
    return text.format(**kwargs) if kwargs else text


def error(exc: Exception) -> str:
    """رسالة خطأ مترجَمة من كود الاستثناء، أو رسالته الأصلية كاحتياط."""
    context = getattr(exc, "context", None) or {}
    code = context.get("code")
    if code and f"error.{code}" in STRINGS:
        try:
            return t(f"error.{code}", **_error_params(context))
        except (KeyError, IndexError):
            pass  # سياق ناقص — الرسالة الأصلية أفضل من انهيار
    return getattr(exc, "message", str(exc))


def _error_params(context: dict) -> dict:
    """توسيع السياق بمتغيّرات مشتقّة تحتاجها بعض الرسائل.

    الخدمة ترفع رمزاً خاماً ("weekly")؛ الرسالة تحتاجه مصرَّفاً في جملة
    ("بياناتك أسبوعية") وبوحدته ("كل 12 أسبوعاً"). التصريف شأن اللغة لا
    شأن services/ingest.py.

    اسم المتغيّر واحد في الصياغتين ({granularity})، وقيمته هي التي تتبدّل
    باللغة — عبر t() المتداخل. أسماء مختلفة لكل لغة كانت ستكسر شرط تطابق
    المتغيّرات، وهو شرط يحرس من خطأ أسوأ: صياغة تنهار للغة واحدة فقط.
    """
    params = dict(context)
    granularity = context.get("granularity")
    if granularity:
        params["granularity"] = t(f"granularity.{granularity}")
        params["unit"] = t(f"granularity.unit.{granularity}")
    return params


def _is_bare_month_label(text: str) -> bool:
    """هل التسمية *شهرٌ مجرّد* (اسم شهر + سنة، أو YYYY-MM) لا أدقّ ولا أخشن؟

    هذا وحده ما يُترجَم: أسماء الأشهر هي التي تختلف بين العربية والإنجليزية.
    "W1 2023" و"Q1 2023" و"2023" و"01 Jan 2023" ليست أشهراً مجرّدة — كلها
    تسقط على أول الشهر عند التحليل، فترجمتها إلى اسم شهر تطمس أسبوعها/ربعها/
    سنتها/يومها وتصيّر فتراتٍ متمايزة تسميةً واحدة مكرّرة. راجع
    services.ingest.parse_month_label.
    """
    from services.ingest import ARABIC_MONTHS as _AR_MONTHS

    if _BARE_MONTH_NAME.match(text) or _ISO_YEAR_MONTH.match(text):
        return True
    # عربي: "ديسمبر 2022" — اسم شهر عربي متبوعاً بسنة فقط (لا يوم)
    for name in _AR_MONTHS:
        if text.startswith(name) and _JUST_A_YEAR.fullmatch(text[len(name):].strip()):
            return True
    return False


def format_month(label: str) -> str:
    """إعادة صياغة تسمية *شهر مجرّد* باللغة الحالية.

    ما ليس شهراً مجرّداً يُترك كما هو: تسمية أسبوع/ربع/سنة/يوم من ملف
    المستخدم ("W1 2023") ليست خطأً يُصحَّح، بل بياناته — وترجمتها إلى اسم
    شهر تطمس حبيبتها. (كان الحارس القديم `parsed is None` يكفي حين كانت
    parse_month_label تعجز عن "W1 2023"؛ بعدما صارت تفهمها لزم فحص الشكل.)
    """
    from services.ingest import parse_month_label

    text = str(label).strip()
    if not _is_bare_month_label(text):
        return label
    parsed = parse_month_label(text)
    if parsed is None:
        return label
    names = ARABIC_MONTHS if current_language() == "ar" else ENGLISH_MONTHS
    return f"{names[parsed.month - 1]} {parsed.year}"


def format_months(labels: list[str]) -> list[str]:
    return [format_month(label) for label in labels]


def format_recommendation(recommendation) -> str:
    """رسالة التوصية باللغة الحالية.

    لا تستخدم `recommendation.as_message()`: تلك عربية ثابتة للسجل
    والتخزين. الكيان يقرر *أي* صياغة تنطبق (message_code)، وهنا نترجمها.
    """
    return t(
        f"rec.{recommendation.message_code}",
        quantity=f"{recommendation.recommended_quantity:,.0f}",
        product=recommendation.product_name,
        pct=abs(recommendation.expected_demand_change_pct),
    )


def format_reason(recommendation) -> str:
    """نص السبب باللغة الحالية، مبنيّاً من أجزائه.

    يتراجع إلى `recommendation.reason` (عربي) للتوصيات المقروءة من قاعدة
    البيانات: تلك تحمل النص المخزَّن ولا تحمل الأجزاء. الاحتياط عربي
    صريح خير من فراغ.
    """
    parts = getattr(recommendation, "reason_parts", ())
    if not parts:
        return recommendation.reason

    rendered = []
    for part in parts:
        if part.code == "risk_level":
            level = t(f"risk.{part.params['level']}")
            rendered.append(f"{level} ({part.params['score']:.0f}/100)")
        else:
            rendered.append(t(f"reason.{part.code}", **part.params))
    return " | ".join(rendered)


def render_language_switcher() -> None:
    """مبدّل اللغة — أعلى الشريط الجانبي، قبل كل شيء.

    موضعه مقصود: زائر لا يقرأ العربية يجب أن يجد المخرج قبل أن يقرر
    أن الأداة ليست له.
    """
    with st.sidebar:
        codes = list(LANGUAGES)
        current = current_language()
        chosen = st.radio(
            "Language / اللغة",
            codes,
            index=codes.index(current),
            format_func=lambda code: LANGUAGES[code],
            horizontal=True,
            label_visibility="collapsed",
            key="_language_radio",
        )
        if chosen != current:
            st.session_state[SESSION_KEY] = chosen
            # الرابط أيضاً — كي تنجو اللغة من إعادة التحميل وتكون قابلة
            # للمشاركة. الاثنان معاً: session_state للتنقّل، والرابط للبقاء.
            try:
                st.query_params[QUERY_PARAM] = chosen
            except Exception:  # noqa: BLE001
                pass  # لا جلسة (اختبار) — session_state يكفي
            st.rerun()
        st.divider()


# ---------------------------------------------------------------------------
# القاموس
# ---------------------------------------------------------------------------
STRINGS: dict[str, dict[str, str]] = {
    # ---- عام ----
    "app.title": {
        "ar": "🔮 نظام تحليل وتنبؤ أوامر التصنيع",
        "en": "🔮 Manufacturing Demand Forecasting",
    },
    "app.load_failed": {
        "ar": "تعذّر تحميل البيانات: {detail}",
        "en": "Could not load data: {detail}",
    },
    "common.product": {"ar": "المنتج", "en": "Product"},
    "common.quantity": {"ar": "الكمية", "en": "Quantity"},
    "common.period": {"ar": "الفترة", "en": "Period"},
    "common.risk": {"ar": "الخطورة", "en": "Risk"},
    "common.level": {"ar": "المستوى", "en": "Level"},
    "common.model": {"ar": "النموذج", "en": "Model"},
    "common.confidence": {"ar": "ثقة التقييم", "en": "Assessment confidence"},
    "common.wape": {"ar": "دقّة WAPE", "en": "WAPE accuracy"},
    "common.reason": {"ar": "السبب", "en": "Reason"},
    "common.demand_change": {"ar": "تغيّر الطلب %", "en": "Demand change %"},
    "common.recommended_qty": {"ar": "الكمية الموصى بها", "en": "Recommended qty"},
    "common.duration_ms": {"ar": "زمن (ms)", "en": "Time (ms)"},
    "common.compute": {"ar": "الحساب", "en": "Compute"},
    "common.all_models": {"ar": "كل النماذج", "en": "All models"},
    "common.all_models_help": {
        "ar": "أدقّ، لكن دقائق على كتالوج كامل بدل ثانية واحدة.",
        "en": "More accurate, but minutes for a full catalogue instead of one second.",
    },
    # ---- تقرير التحقّق (services/validation.py) ----
    "val.title": {
        "ar": ":material/fact_check: تقرير التحقّق — كيف كانت الأداة ستؤدّي على تاريخك؟",
        "en": ":material/fact_check: Validation report — how would this have performed on your history?",
    },
    "val.explainer": {
        "ar": "تُشغَّل الأداة على عدة نقاط في ماضيك: تتدرّب على ما قبل النقطة فقط، "
              "وتُقارَن توصيتها بما حدث فعلاً بعدها. لا شيء من نافذة الاختبار "
              "يدخل التدريب.",
        "en": "The tool is run at several points in your past: trained only on what "
              "came before each point, then compared against what actually happened "
              "after it. Nothing from the test window enters training.",
    },
    "val.compute": {"ar": "احسب تقرير التحقّق", "en": "Compute validation report"},
    "val.empty": {
        "ar": "اضغط الزر أعلاه لتشغيل الأداة على تاريخك.",
        "en": "Click above to run the tool against your own history.",
    },
    "val.kpi_measured": {"ar": "قِيست دقّتها", "en": "Accuracy measured"},
    "val.kpi_measured_help": {
        "ar": "منتج لم يقع فيه طلب في نافذة الاختبار لا دقّة تُقاس له — "
              "لا يُحتسب هنا ولا يُحذف من المقام.",
        "en": "A product with no demand in the test window has no measurable "
              "accuracy — it is neither counted here nor dropped from the total.",
    },
    "val.kpi_wape": {"ar": "وسيط WAPE", "en": "Median WAPE"},
    "val.kpi_wape_help": {
        "ar": "نسبة الخطأ إلى إجمالي الطلب الفعلي. أقل = أفضل.",
        "en": "Error as a share of total actual demand. Lower is better.",
    },
    "val.kpi_beat_naive": {"ar": "تفوّقت على الساذج", "en": "Beat naive"},
    "val.kpi_beat_naive_help": {
        "ar": "نسبة المنتجات التي تفوّقت فيها الأداة على تكرار آخر قيمة — "
              "على نفس النافذة ونفس الأفق.",
        "en": "Share of products where the tool beat simply repeating the last "
              "value — same window, same horizon.",
    },
    "val.kpi_mase": {"ar": "وسيط MASE", "en": "Median MASE"},
    "val.kpi_mase_help": {
        "ar": "الخطأ منسوباً إلى خطأ الساذج بخطوة واحدة داخل التدريب. مرجع "
              "قابل للمقارنة بين منتجات مختلفة الأحجام.",
        "en": "Error scaled by the naive one-step error inside training. "
              "Comparable across products of different sizes.",
    },
    "val.unmeasured_note": {
        "ar": "خارج القياس: {no_demand} منتجاً بلا طلب في نافذة الاختبار، "
              "و{skipped} تعذّر تشغيلها. كلاهما ضمن المقام أعلاه.",
        "en": "Outside measurement: {no_demand} products had no demand in the test "
              "window, and {skipped} could not be run. Both are in the total above.",
    },
    "val.col_origins": {"ar": "نقاط الاختبار", "en": "Test points"},
    "val.col_mase": {"ar": "MASE", "en": "MASE"},
    "val.col_vs_naive": {"ar": "مقابل الساذج", "en": "vs naive"},
    "val.better": {"ar": "أفضل", "en": "better"},
    "val.worse": {"ar": "أسوأ", "en": "worse"},
    "val.download": {"ar": "⬇ تحميل التقرير (Excel)", "en": "⬇ Download report (Excel)"},
    "val.sheet_measured": {"ar": "المقيسة", "en": "Measured"},
    "val.sheet_unmeasured": {"ar": "خارج القياس", "en": "Not measured"},
    "val.reason_no_demand": {
        "ar": "لا طلب فعلي في نافذة الاختبار",
        "en": "No actual demand in the test window",
    },
    "risk.low": {"ar": "🟢 منخفضة", "en": "🟢 Low"},
    "risk.medium": {"ar": "🟡 متوسطة", "en": "🟡 Medium"},
    "risk.high": {"ar": "🔴 عالية", "en": "🔴 High"},

    # ---- تصنيف الطلب ----
    "class.smooth": {"ar": "منتظم", "en": "Smooth"},
    "class.erratic": {"ar": "متذبذب", "en": "Erratic"},
    "class.intermittent": {"ar": "متقطّع", "en": "Intermittent"},
    "class.lumpy": {"ar": "متكتّل", "en": "Lumpy"},
    "class.dead": {"ar": "بلا مبيعات", "en": "No sales"},
    "class.smooth.help": {
        "ar": "طلب كل شهر بأحجام متماسكة — العائلة الموسمية في مجالها.",
        "en": "Demand every month at consistent sizes — seasonal models apply here.",
    },
    "class.erratic.help": {
        "ar": "يحدث غالباً، لكن بأحجام شديدة التقلب.",
        "en": "Happens often, but at wildly varying sizes.",
    },
    "class.intermittent.help": {
        "ar": "فجوات كثيرة، أحجام متماسكة — مجال Croston/TSB.",
        "en": "Many gaps, consistent sizes — Croston/TSB territory.",
    },
    "class.lumpy.help": {
        "ar": "فجوات *و* تقلب — الأصعب على كل النماذج.",
        "en": "Gaps *and* volatility — the hardest case for every model.",
    },
    "class.dead.help": {
        "ar": "لا طلب قط — لا نموذج ينطبق.",
        "en": "Never any demand — no model applies.",
    },

    # ---- التنقّل ----
    "nav.executive": {"ar": "النظرة التنفيذية", "en": "Executive"},
    "nav.forecasting": {"ar": "التنبؤ", "en": "Forecasting"},
    "nav.intelligence": {"ar": "ذكاء المنتج", "en": "Product Intelligence"},
    "nav.advanced": {"ar": "التحليل المتقدّم", "en": "Advanced Analytics"},

    # ---- البيانات والرفع ----
    "data.header": {"ar": ":material/folder: البيانات", "en": ":material/folder: Data"},
    "data.your_file": {
        "ar": "ملفك: **{products}** منتج × **{months}** {unit}",
        "en": "Your file: **{products}** products × **{months}** {unit}",
    },
    "data.notes": {
        "ar": ":material/warning: ملاحظات على الملف ({count})",
        "en": ":material/warning: Notes on your file ({count})",
    },
    "data.back_to_demo": {"ar": "العودة لبيانات العرض", "en": "Back to demo data"},
    "data.demo_active": {
        "ar": "بيانات عرض اصطناعية معروضة الآن. ارفع ملفك لتحليله.",
        "en": "Showing synthetic demo data. Upload your file to analyse it.",
    },
    "data.uploader": {"ar": "CSV أو Excel", "en": "CSV or Excel"},
    "data.uploader_help": {
        "ar": "عمود للمنتج + عمود لكل شهر. أو ثلاثة أعمدة: منتج/شهر/كمية.",
        "en": "One product column + one column per month. Or three columns: product/month/quantity.",
    },
    "data.template": {"ar": "⬇ نموذج CSV", "en": "⬇ CSV template"},
    "data.privacy_hosted": {
        "ar": ":material/lock: ملفك يُحلَّل في الذاكرة ولا يُحفَظ على الخادم. "
              "يختفي بإغلاق التبويب، ولا يراه زائر آخر.",
        "en": ":material/lock: Your file is analysed in memory and never written to the server. "
              "It disappears when you close the tab, and no other visitor sees it.",
    },
    "data.privacy_local": {
        "ar": ":material/lock: ملفك في ذاكرة الجلسة ولا يُكتب في قاعدة البيانات. "
              "يختفي بإعادة التشغيل.",
        "en": ":material/lock: Your file lives in session memory and is never written to the database. "
              "It disappears on restart.",
    },
    "data.read_failed": {
        "ar": "تعذّرت قراءة الملف: {detail}",
        "en": "Could not read the file: {detail}",
    },
    "data.columns_found": {
        "ar": "الأعمدة التي وجدتها: {columns}",
        "en": "Columns found: {columns}",
    },
    "data.map_columns": {
        "ar": ":material/link: ربط الأعمدة يدوياً",
        "en": ":material/link: Map columns manually",
    },
    "data.map_columns_help": {
        "ar": "لم نتعرّف على أعمدة ملفك تلقائياً. اختر أيّ عمود هو أيّ —"
              " إن كان ملفك بشكل «صفّ لكل منتج/شهر».",
        "en": "We couldn't recognise your file's columns automatically. "
              "Pick which column is which — if your file has one row per "
              "product/month record.",
    },
    "data.map_choose": {"ar": "— اختر —", "en": "— choose —"},
    "data.map_product": {"ar": "عمود المنتج", "en": "Product column"},
    "data.map_month": {"ar": "عمود الشهر", "en": "Month column"},
    "data.map_quantity": {"ar": "عمود الكمية", "en": "Quantity column"},
    "data.map_apply": {"ar": "استخدم هذا الربط", "en": "Use this mapping"},
    "data.map_incomplete": {
        "ar": "اختر الأعمدة الثلاثة كلها للمتابعة.",
        "en": "Pick all three columns to continue.",
    },
    "data.map_duplicate": {
        "ar": "لا يصلح العمود نفسه لدورين — اختر ثلاثة أعمدة مختلفة.",
        "en": "The same column can't serve two roles — pick three different columns.",
    },

    # ---- ملف المخزون (اختياري، يتبع أداة رفع المبيعات في الشريط) ----
    "stock.header": {"ar": ":material/inventory_2: المخزون", "en": ":material/inventory_2: Stock"},
    "stock.none_active": {
        "ar": "لا ملف مخزون مرفوع — الكميات المقترحة تعرض الطلب المتوقَّع "
              "كاملاً، وعامل نفاد المخزون غير محسوب.",
        "en": "No stock file uploaded — suggested quantities show full "
              "expected demand, and stock-depletion risk is not computed.",
    },
    "stock.uploader": {"ar": "CSV أو Excel", "en": "CSV or Excel"},
    "stock.uploader_help": {
        "ar": "عمودان: اسم المنتج، والمخزون الحالي.",
        "en": "Two columns: product name, and current stock.",
    },
    "stock.template": {"ar": "⬇ نموذج CSV", "en": "⬇ CSV template"},
    "stock.loaded": {
        "ar": "مخزون **{count}** منتج محمَّل — الكميات المقترحة تخصمه، "
              "وعامل نفاد المخزون محسوب الآن.",
        "en": "Stock for **{count}** products loaded — suggested quantities "
              "net it off, and stock-depletion risk is now computed.",
    },
    "stock.clear": {"ar": "إزالة ملف المخزون", "en": "Remove stock file"},
    "stock.read_failed": {
        "ar": "تعذّرت قراءة ملف المخزون: {detail}",
        "en": "Could not read the stock file: {detail}",
    },
    "stock.map_columns": {
        "ar": ":material/link: ربط الأعمدة يدوياً", "en": ":material/link: Map columns manually",
    },
    "stock.map_columns_help": {
        "ar": "لم نتعرّف على أعمدة ملفك تلقائياً. اختر أيّ عمود هو المنتج، "
              "وأيّ عمود هو المخزون.",
        "en": "We couldn't recognise your file's columns automatically. "
              "Pick which column is the product, and which is the stock level.",
    },
    "stock.map_stock": {"ar": "عمود المخزون", "en": "Stock column"},

    # ---- أخطاء الرفع (من services/ingest.py عبر code) ----
    "error.unreadable_file": {
        "ar": "تعذّرت قراءة الملف — تأكّد أنه CSV أو Excel صالح.",
        "en": "Could not read the file — make sure it is a valid CSV or Excel file.",
    },
    "error.empty_file": {"ar": "الملف فارغ.", "en": "The file is empty."},
    "error.no_months": {
        "ar": "لم يُفهَم أي عمود كتاريخ. الأشكال المقبولة: "
              "'يناير 2023'، 'Jan 2023'، '2023-01'، '2024-01-15'.",
        "en": "No column was understood as a date. Accepted formats: "
              "'Jan 2023', 'January 2023', '2023-01', '2024-01-15'.",
    },
    "error.no_stock_columns": {
        "ar": "لم يُفهَم عمود المنتج أو عمود المخزون في هذا الملف.",
        "en": "Could not recognise the product column or the stock column "
              "in this file.",
    },
    "error.too_few_months": {
        "ar": "{months} {unit} فقط — الحد الأدنى {minimum}.",
        "en": "Only {months} {unit} — the minimum is {minimum}.",
    },
    "granularity.daily": {"ar": "يومية", "en": "daily"},
    "granularity.weekly": {"ar": "أسبوعية", "en": "weekly"},
    "granularity.monthly": {"ar": "شهرية", "en": "monthly"},
    "granularity.quarterly": {"ar": "ربعية", "en": "quarterly"},
    "granularity.yearly": {"ar": "سنوية", "en": "yearly"},
    "granularity.unit.daily": {"ar": "يوماً", "en": "days"},
    "granularity.unit.weekly": {"ar": "أسبوعاً", "en": "weeks"},
    "granularity.unit.monthly": {"ar": "شهراً", "en": "months"},
    "granularity.unit.quarterly": {"ar": "ربعاً", "en": "quarters"},
    "granularity.unit.yearly": {"ar": "سنة", "en": "years"},
    # صيغة المفرد — لعناوين المحاور والتسميات التي تصف فترة واحدة لا عدداً.
    "granularity.one.daily": {"ar": "اليوم", "en": "Day"},
    "granularity.one.weekly": {"ar": "الأسبوع", "en": "Week"},
    "granularity.one.monthly": {"ar": "الشهر", "en": "Month"},
    "granularity.one.quarterly": {"ar": "الربع", "en": "Quarter"},
    "granularity.one.yearly": {"ar": "السنة", "en": "Year"},
    # صيغة الجمع — لتسميات تصف عدّة فترات بلا رقم يسبقها ("أسابيع (>0)").
    "granularity.many.daily": {"ar": "أيام", "en": "days"},
    "granularity.many.weekly": {"ar": "أسابيع", "en": "weeks"},
    "granularity.many.monthly": {"ar": "أشهر", "en": "months"},
    "granularity.many.quarterly": {"ar": "أرباع", "en": "quarters"},
    "granularity.many.yearly": {"ar": "سنوات", "en": "years"},

    "error.no_products": {
        "ar": "لا منتجات صالحة في الملف.",
        "en": "No valid products in the file.",
    },
    "error.missing_columns": {
        "ar": "الملف يحتاج عمود أسماء وعمود شهر واحداً على الأقل.",
        "en": "The file needs a name column and at least one month column.",
    },
    "error.unknown_mapped_column": {
        "ar": "العمود المختار غير موجود في الملف: {column}",
        "en": "The chosen column doesn't exist in the file: {column}",
    },
    "error.duplicate_mapped_columns": {
        "ar": "اختر ثلاثة أعمدة مختلفة — العمود نفسه لا يصلح لدورين.",
        "en": "Pick three different columns — the same column can't serve two roles.",
    },

    # ---- النظرة التنفيذية ----
    "exec.title": {
        "ar": ":material/dashboard: النظرة التنفيذية",
        "en": ":material/dashboard: Executive Overview",
    },
    "exec.computing": {"ar": "جارٍ الحساب...", "en": "Computing..."},
    "exec.recompute": {"ar": "حساب الكتالوج", "en": "Compute catalogue"},
    "exec.ephemeral_user": {
        "ar": ":material/lock: محسوب في الذاكرة ولا يُحفَظ — بياناتك ملكك.",
        "en": ":material/lock: Computed in memory, never stored — your data is yours.",
    },
    "exec.ephemeral_hosted": {
        "ar": ":material/lock: محسوب في الذاكرة ولا يُحفَظ — الوضع المستضاف.",
        "en": ":material/lock: Computed in memory, never stored — hosted mode.",
    },
    "exec.empty": {
        "ar": "لا توصيات بعد. اضغط **حساب الكتالوج** في الشريط الجانبي — "
              "النماذج الخفيفة تُنهي الكتالوج في نحو ثانية.",
        "en": "No recommendations yet. Press **Compute catalogue** in the sidebar — "
              "the light models finish the catalogue in about a second.",
    },
    "exec.batch_done": {
        "ar": "تم حساب {count} منتجاً في {seconds:.1f}s.",
        "en": "Computed {count} products in {seconds:.1f}s.",
    },
    "exec.batch_partial": {
        "ar": "تم حساب {ok} من {total} في {seconds:.1f}s. فشل {failed} — "
              "غالباً منتجات بلا مبيعات كافية.",
        "en": "Computed {ok} of {total} in {seconds:.1f}s. {failed} failed — "
              "usually products without enough sales.",
    },
    "exec.failure_details": {"ar": "تفاصيل الفشل", "en": "Failure details"},
    "exec.kpi_assessed": {"ar": "منتجات مُقيَّمة", "en": "Products assessed"},
    "exec.kpi_actionable": {"ar": "تحتاج إنتاجاً", "en": "Need production"},
    "exec.kpi_high_risk": {"ar": "منها عالية الخطورة", "en": "Of those, high risk"},
    "exec.kpi_total_qty": {"ar": "إجمالي الكمية الموصى بها", "en": "Total recommended qty"},
    "exec.needs_decision": {
        "ar": "يحتاج قراراً — مرتّب بالخطورة",
        "en": "Needs a decision — ordered by risk",
    },
    "exec.needs_decision_help": {
        "ar": "المنتجات التي يوصى بإنتاج كمية منها. الخطورة تحدد الأولوية، "
              "لا الحاجة نفسها.",
        "en": "Products with a recommended quantity. Risk sets the priority, "
              "not the need itself.",
    },
    "exec.nothing_actionable": {
        "ar": "لا منتج يحتاج إنتاجاً حسب التوصيات الحالية.",
        "en": "No product needs production under the current recommendations.",
    },
    "exec.dormant_risky": {
        "ar": "⏸️ خامل لكن عالي الخطورة ({count})",
        "en": "⏸️ Idle but high risk ({count})",
    },
    "exec.dormant_help": {
        "ar": "أقل من {threshold} وحدة متوقَّعة الفترة القادمة — لا قرار إنتاج. "
              "خطورتها عالية بسبب تاريخ متذبذب: معلومة تستحق النظر (منتج "
              "يموت؟) لا إجراءً. فُصلت كي لا تزاحم ما يحتاج قراراً فعلياً.",
        "en": "Fewer than {threshold} units expected next period — no production "
              "decision. High risk from a volatile history: worth noticing (a "
              "product dying?) but not an action. Separated so it does not crowd "
              "out what actually needs deciding.",
    },
    "exec.fva_summary": {
        "ar": ":material/query_stats: على {total} منتجاً بمقارنة صالحة: النموذج المختار تفوّق على "
              "التكرار الساذج (Naive) في {beat} منها ({pct:.0f}%). الباقي — "
              "الساذج كافٍ، ولا تعقيد اشترى شيئاً.",
        "en": ":material/query_stats: Across {total} products with a valid comparison: the chosen "
              "model beat the naive baseline in {beat} of them ({pct:.0f}%). "
              "For the rest, naive was enough — complexity bought nothing.",
    },
    "exec.glance_purchase": {
        "ar": "🛒 {urgent} من {total} منتج في آخر خطة شراء محسوبة يحتاج طلباً عاجلاً",
        "en": "🛒 {urgent} of {total} products in the last computed purchase plan need an urgent order",
    },
    "exec.inventory_caveat": {
        "ar": ":material/warning: عامل نفاد المخزون غير محسوب — لا ملف مخزون مرفوع. لذا "
              "ثقة التقييم 80% (4 عوامل من 5) لكل المنتجات. ارفع ملف "
              "المخزون من الشريط الجانبي لتفعيله.",
        "en": ":material/warning: Stock-depletion risk is not computed — no stock file "
              "uploaded. That is why every product shows 80% confidence "
              "(4 factors of 5). Upload a stock file from the sidebar to "
              "enable it.",
    },
    "exec.inventory_active": {
        "ar": ":material/inventory_2: عامل نفاد المخزون محسوب من ملف المخزون المرفوع لهذه "
              "الجلسة — الكميات المعروضة تخصم المخزون المتاح.",
        "en": ":material/inventory_2: Stock-depletion risk is computed from this session's "
              "uploaded stock file — quantities shown net off available stock.",
    },

    # ---- بلا تاريخ مبيعات — استعارة نمط منتج مشابه ----
    "exec.no_history": {
        "ar": "🆕 بلا تاريخ مبيعات ({count})",
        "en": "🆕 No sales history ({count})",
    },
    "exec.no_history_help": {
        "ar": "لا مبيعات لهذه المنتجات في البيانات المرفوعة إطلاقاً. لا "
              "يمكن التمييز من البيانات وحدها بين منتج جديد لم يُطلَق بعد "
              "ومنتج توقّف تماماً — كلاهما يظهر بنفس الشكل: أصفار كاملة.",
        "en": "These products have no sales at all in the uploaded data. The "
              "data alone can't distinguish a genuinely new, not-yet-launched "
              "product from a discontinued one — both look identical: all "
              "zeros.",
    },
    "exec.borrow_help": {
        "ar": "إن كان أحدها منتجاً جديداً فعلاً، اختر منتجاً مشابهاً "
              "قائماً لتُستعار منه توصية أولية — تُوسَم بوضوح أنها مُستعارة "
              "لا محسوبة. إن كان متوقّفاً، اتركه كما هو — لا إجراء مطلوباً.",
        "en": "If one of these is genuinely a new product, pick a similar "
              "existing one to borrow an initial estimate from — clearly "
              "labelled as borrowed, not computed. If it's discontinued, "
              "leave it as is — no action needed.",
    },
    "exec.borrow_target": {"ar": "المنتج بلا تاريخ", "en": "Product with no history"},
    "exec.borrow_source": {"ar": "استعارة النمط من", "en": "Estimate from"},
    "exec.borrow_apply": {"ar": "استعر هذا التقدير", "en": "Borrow this estimate"},
    "exec.borrow_no_source": {
        "ar": "لا منتج آخر في الكتالوج يمكن الاستعارة منه.",
        "en": "No other product in the catalogue to estimate from.",
    },

    # ---- التوفيق الهرمي — إجمالي كل فئة، Bottom-Up ----
    "exec.category_totals": {"ar": ":material/category: حسب الفئة", "en": ":material/category: By category"},
    "exec.category_totals_help": {
        "ar": "إجمالي كل فئة هو مجموع توصيات منتجاتها بالضبط — لا تقريباً، "
              "ولا تنبؤاً مستقلاً يُصالَح لاحقاً. منتج بلا فئة معروفة "
              "يُستبعد من كل الإجماليات، لا يُحتسب في فئة مخترعة.",
        "en": "Each category's total is exactly the sum of its products' "
              "recommended quantities — not an approximation, and not an "
              "independently-computed forecast reconciled after the fact. A "
              "product with no known category is excluded from every total, "
              "not counted in an invented catch-all.",
    },
    "common.category": {"ar": "الفئة", "en": "Category"},
    "common.product_count": {"ar": "عدد المنتجات", "en": "Products"},

    # ---- التنبؤ ----
    "fc.title": {"ar": ":material/insights: التنبؤ", "en": ":material/insights: Forecasting"},
    "fc.subtitle": {
        "ar": "يُشغّل كل النماذج المنطبقة، يقيّمها على بيانات لم ترَها، "
              "ويختار الأفضل بالأدلة.",
        "en": "Runs every applicable model, scores each on data it never saw, "
              "and picks the winner on evidence.",
    },
    "fc.settings": {"ar": "إعدادات التنبؤ", "en": "Forecast settings"},
    "fc.horizon": {"ar": "أفق التنبؤ ({unit})", "en": "Forecast horizon ({unit})"},
    "fc.full_family_help": {
        "ar": "يضيف ETS/SARIMA/Prophet/XGBoost/RandomForest — أبطأ (~1s).",
        "en": "Adds ETS/SARIMA/Prophet/XGBoost/RandomForest — slower (~1s).",
    },
    "fc.training": {"ar": "تدريب النماذج وتقييمها...", "en": "Training and scoring models..."},
    "fc.failed": {"ar": "تعذّر التنبؤ: {detail}", "en": "Forecast failed: {detail}"},
    "fc.failed_help": {
        "ar": "منتج بلا مبيعات كافية لا ينطبق عليه أي نموذج. هذا رفض صريح "
              "لا عطل — راجع صفحة **ذكاء المنتج** لتصنيف الطلب.",
        "en": "A product without enough sales has no applicable model. This is an "
              "explicit refusal, not a failure — see **Product Intelligence** for "
              "its demand class.",
    },
    "fc.winner": {"ar": "النموذج الفائز", "en": "Winning model"},
    "fc.next_period": {"ar": "تنبؤ الفترة القادمة", "en": "Next-period forecast"},
    "fc.demand_class": {"ar": "تصنيف الطلب", "en": "Demand class"},
    "fc.evaluated": {"ar": "نماذج قُيِّمت", "en": "Models scored"},
    "fc.evaluated_help": {
        "ar": "المقيَّم = دُرِّب على جزء من السلسلة واختُبر على الباقي. "
              "صفر يعني أن السلسلة أقصر من أن تُقسَّم — لا أن النماذج فشلت.",
        "en": "Scored = trained on part of the series and tested on the rest. "
              "Zero means the series is too short to split — not that the models "
              "failed.",
    },
    "fc.chart_title": {
        "ar": "الطلب الفعلي والمتوقَّع — {model}",
        "en": "Actual vs forecast demand — {model}",
    },
    "fc.actual": {"ar": "فعلي", "en": "Actual"},
    "fc.forecast_of": {"ar": "تنبؤ {model}", "en": "{model} forecast"},
    "fc.upper": {"ar": "حد أعلى 95%", "en": "Upper 95%"},
    "fc.interval": {"ar": "فترة الثقة 95%", "en": "95% confidence"},
    "fc.comparison": {"ar": "مقارنة النماذج", "en": "Model comparison"},
    "fc.metric_cumulative": {
        "ar": "المقياس: **الخطأ التراكمي** — سلسلة متقطّعة، والقرار الإنتاجي "
              "يستهلك إجمالي الأفق لا دقة كل فترة.",
        "en": "Metric: **cumulative error** — an intermittent series, and the "
              "production decision consumes the horizon total, not per-period "
              "accuracy.",
    },
    "fc.metric_rmse": {
        "ar": "المقياس: **RMSE** — سلسلة منتظمة.",
        "en": "Metric: **RMSE** — a smooth series.",
    },
    "fc.metric_marked": {
        "ar": "{note} العمود المعلَّم ★ هو ما رُتِّب به.",
        "en": "{note} The column marked ★ is the one used for ranking.",
    },
    "fc.no_evaluation": {
        "ar": "**لم يُقيَّم أي نموذج.** السلسلة ({nonzero} {unit} بمبيعات من "
              "{total}) أقصر من أن تُقسَّم إلى تدريب واختبار.\n\nلذا اختار "
              "المحرك **{model}** بقاعدته المعلنة: بلا دليل على أن التعقيد "
              "يفيد، يفوز الأبسط. الرقم أعلاه تنبؤ حقيقي، لكن **بلا مقياس "
              "دقة يسنده** — تعامل معه بحذر.",
        "en": "**No model could be scored.** The series ({nonzero} selling {unit} "
              "of {total}) is too short to split into train and test.\n\nSo the "
              "engine chose **{model}** by its stated rule: without evidence that "
              "complexity helps, the simplest wins. The number above is a real "
              "forecast, but **nothing measures its accuracy** — treat it with "
              "care.",
    },
    "fc.inapplicable": {
        "ar": "نماذج لم تنطبق ({count})",
        "en": "Models that did not apply ({count})",
    },
    "fc.recommendation": {"ar": "التوصية", "en": "Recommendation"},
    "fc.rec_failed": {"ar": "تعذّرت التوصية: {detail}", "en": "Recommendation failed: {detail}"},
    "fc.cumulative_error": {"ar": "خطأ تراكمي", "en": "Cumulative error"},

    # ---- ذكاء المنتج ----
    "pi.title": {"ar": ":material/psychology: ذكاء المنتج", "en": ":material/psychology: Product Intelligence"},
    "pi.settings": {"ar": ":material/tune: الإعدادات", "en": ":material/tune: Settings"},
    "pi.classification": {"ar": "تصنيف الطلب", "en": "Demand classification"},
    "pi.class": {"ar": "التصنيف", "en": "Class"},
    "pi.adi_help": {
        "ar": "متوسط الفترة بين الطلبات. 1.0 = كل فترة.",
        "en": "Average interval between demands. 1.0 = every period.",
    },
    "pi.cv2_help": {
        "ar": "تقلب أحجام الطلب غير الصفري.",
        "en": "Volatility of non-zero demand sizes.",
    },
    "pi.selling_periods": {"ar": "{unit} بمبيعات", "en": "{unit} with sales"},
    "pi.dead_product": {
        "ar": "لا مبيعات لهذا المنتج قط — لا تنبؤ ولا خطورة.",
        "en": "This product has never sold — no forecast, no risk.",
    },
    "pi.history": {"ar": "تاريخ الطلب", "en": "Demand history"},
    "pi.computing_risk": {"ar": "حساب الخطورة...", "en": "Computing risk..."},
    "pi.analysis_failed": {"ar": "تعذّر التحليل: {detail}", "en": "Analysis failed: {detail}"},
    "pi.risk_breakdown": {"ar": "تفكيك الخطورة", "en": "Risk breakdown"},
    "pi.score": {"ar": "الدرجة", "en": "Score"},
    "pi.confidence_help": {
        "ar": "نسبة العوامل التي أمكن حسابها.",
        "en": "Share of factors that could be computed.",
    },
    "pi.factor_chart": {"ar": "مساهمة كل عامل (0-100)", "en": "Each factor's contribution (0-100)"},
    "pi.missing_factors": {
        "ar": "**عوامل غير محسوبة:** {names}. استُبعدت من الحساب وأُعيدت "
              "موازنة الباقي — لم تُعامَل كصفر. الصفر يعني *قِسنا ولا خطورة*؛ "
              "الغياب يعني *لا نعرف*.",
        "en": "**Factors not computed:** {names}. They were excluded and the "
              "remaining weights renormalised — they were not treated as zero. "
              "Zero means *we measured, no risk*; absence means *we don't know*.",
    },
    "pi.weights": {"ar": "أوزان العوامل", "en": "Factor weights"},
    "pi.factor": {"ar": "العامل", "en": "Factor"},
    "pi.weight": {"ar": "الوزن", "en": "Weight"},
    "pi.computed": {"ar": "محسوب؟", "en": "Computed?"},
    "common.yes": {"ar": "نعم", "en": "Yes"},
    "common.no": {"ar": "لا", "en": "No"},
    "pi.weights_caveat": {
        "ar": "معايرة أولية بلا بيانات تحقّق — تُضبط حين يتراكم "
              "`production_plans.actual_quantity` مقابل `planned_quantity`.",
        "en": "An initial calibration with no validation data behind it — to be "
              "tuned once `production_plans.actual_quantity` accumulates against "
              "`planned_quantity`.",
    },
    "pi.stored_history": {"ar": "سجل النماذج المحفوظ", "en": "Stored model history"},
    "pi.history_local_only": {
        "ar": ":material/lock: سجل النماذج التاريخي متاح في الوضع المحلي فقط — بياناتك لا "
              "تُحفَظ. كل ما فوق محسوب لجلستك الآن.",
        "en": ":material/lock: Historical model records are local-mode only — your data is not "
              "stored. Everything above was computed for this session.",
    },
    "pi.no_history": {
        "ar": "لا سجل محفوظ لهذا المنتج. شغّل الحساب من **النظرة التنفيذية**.",
        "en": "No stored records for this product. Run the compute from "
              "**Executive**.",
    },
    "pi.is_best": {"ar": "الأفضل؟", "en": "Best?"},
    "pi.evaluated_at": {"ar": "التقييم", "en": "Scored at"},
    "pi.last_recommendation": {"ar": "آخر توصية محفوظة", "en": "Last stored recommendation"},
    "factor.demand_volatility": {"ar": "تقلب الطلب", "en": "Demand volatility"},
    "factor.stock_depletion_risk": {"ar": "نفاد المخزون", "en": "Stock depletion"},
    "factor.forecast_accuracy_penalty": {"ar": "عدم دقة التنبؤ", "en": "Forecast inaccuracy"},
    "factor.seasonality_factor": {"ar": "الموسمية", "en": "Seasonality"},
    "factor.growth_rate": {"ar": "معدّل التغيّر", "en": "Rate of change"},

    # ---- التحليل المتقدّم ----
    "adv.title": {
        "ar": ":material/analytics: نظام تحليل وتنبؤ أوامر التصنيع – الإصدار الاحترافي",
        "en": ":material/analytics: Advanced Analytics",
    },
    "adv.notice": {
        "ar": "هذه الصفحة **وصفية**: تستكشف التاريخ الفعلي وتُصدّره — مقارنة "
              "منتجات، كشف قيم شاذة، وإحصاءات وصفية. **لا تتنبّأ**: التنبؤ "
              "يختار نموذجه بالأدلة في صفحة **التنبؤ**.",
        "en": "This page is **descriptive**: it explores and exports actual "
              "history — product comparison, outlier detection, and summary "
              "statistics. It does **not** forecast: model selection is "
              "evidence-based on the **Forecasting** page.",
    },

    # ---- الشريط الجانبي القديم (التحليل المتقدّم) ----
    "old.control_panel": {"ar": ":material/tune: لوحة التحكم", "en": ":material/tune: Controls"},
    "old.select_products": {
        "ar": "اختر المنتج (يمكن اختيار عدة)",
        "en": "Select products (multiple allowed)",
    },
    "old.pick_one": {
        "ar": "الرجاء اختيار منتج واحد على الأقل",
        "en": "Please select at least one product",
    },
    "old.month_range": {"ar": "النطاق ({many})", "en": "Range ({many})"},
    # قيم لا تسميات — الكود يقارن بالرمز، والتسمية تُشتقّ منه.
    # قبل هذا كان dashboard.py يقارن بالنص الحرفي "SARIMA (إذا توفر)"،
    # فترجمة التسمية كانت ستكسر المقارنة بصمت: SARIMA لا يعمل، بلا خطأ.
    "old.outliers": {"ar": "كشف النقاط الشاذة", "en": "Outlier detection"},
    "old.run": {"ar": "تشغيل التحليل المتقدم", "en": "Run advanced analysis"},

    # ---- لوحة التحليل المتقدّم ----
    "old.product_analysis": {
        "ar": ":material/query_stats: تحليل المنتج: {product}",
        "en": ":material/query_stats: Product analysis: {product}",
    },
    "old.total": {"ar": "الإجمالي", "en": "Total"},
    "old.average": {"ar": "المتوسط", "en": "Average"},
    "old.max": {"ar": "⬆ الأعلى", "en": "⬆ Highest"},
    "old.min_nonzero": {"ar": "⬇ الأدنى (غير صفري)", "en": "⬇ Lowest (non-zero)"},
    "old.std": {"ar": "الانحراف المعياري", "en": "Std deviation"},
    "old.median": {"ar": "الوسيط", "en": "Median"},
    "old.nonzero_months": {"ar": "{many} (>0)", "en": "{many} (>0)"},
    "old.cv": {"ar": "معامل الاختلاف", "en": "Coefficient of variation"},
    "old.last_value": {"ar": "آخر قيمة", "en": "Last value"},
    "old.outliers_found": {
        "ar": "تم اكتشاف {count} نقطة شاذة ({many}: {months})",
        "en": "{count} outliers detected ({many}: {months})",
    },
    "old.main_chart": {
        "ar": ":material/show_chart: التاريخ الفعلي",
        "en": ":material/show_chart: Actual history",
    },
    # لا أيقونة هنا عمداً: تُستهلَك كعنوان رسم Plotly (ui/charts.py) لا
    # عنصر Streamlit — رمز :material/...: لن يُعرَض هناك كأيقونة بل كنص خام.
    "old.details_table": {
        "ar": ":material/table_chart: البيانات التفصيلية مع التغيرات",
        "en": ":material/table_chart: Detailed data with changes",
    },
    "old.export": {"ar": "⬇️ تصدير التقارير", "en": "⬇️ Export reports"},
    "old.download_csv": {"ar": "⬇ تحميل CSV (البيانات الفعلية)", "en": "⬇ Download CSV (actual data)"},
    "old.download_excel": {"ar": "⬇ تحميل Excel", "en": "⬇ Download Excel"},
    "old.sheet_data": {"ar": "البيانات", "en": "Data"},
    "old.no_outliers": {"ar": "لم يتم اكتشاف نقاط شاذة", "en": "No outliers detected"},
    "old.comparison_selected": {
        "ar": ":material/compare_arrows: مقارنة المنتجات المختارة",
        "en": ":material/compare_arrows: Selected product comparison",
    },
    "old.footer": {
        "ar": "نظام تحليل وتنبؤ متقدم – يعمل بنماذج ETS، SARIMA، والانحدار الخطي",
        "en": "Advanced analysis and forecasting — powered by ETS, SARIMA and linear regression",
    },
    "old.analysed_range": {
        "ar": ":material/calendar_month: تم تحليل البيانات من {start} إلى {end} ({count} {unit})",
        "en": ":material/calendar_month: Analysed data from {start} to {end} ({count} {unit})",
    },

    # ---- رسالة التوصية (من ProductionRecommendation.message_code) ----
    "rec.stable": {
        "ar": "يوصى بإنتاج {quantity} وحدة من المنتج {product} في الشهر "
              "القادم — الطلب المتوقع مستقر",
        "en": "Produce {quantity} units of {product} next month — "
              "expected demand is steady",
    },
    "rec.rise": {
        "ar": "يوصى بإنتاج {quantity} وحدة من المنتج {product} في الشهر "
              "القادم بسبب ارتفاع الطلب المتوقع بنسبة {pct:.1f}%",
        "en": "Produce {quantity} units of {product} next month — "
              "expected demand is up {pct:.1f}%",
    },
    "rec.fall": {
        "ar": "يوصى بإنتاج {quantity} وحدة من المنتج {product} في الشهر "
              "القادم بسبب انخفاض الطلب المتوقع بنسبة {pct:.1f}%",
        "en": "Produce {quantity} units of {product} next month — "
              "expected demand is down {pct:.1f}%",
    },

    # ---- أجزاء السبب (من ReasonPart) ----
    "reason.no_baseline": {
        "ar": "لا مبيعات في الفترة المرجعية — التوصية من التنبؤ وحده",
        "en": "No sales in the baseline period — the recommendation rests on the "
              "forecast alone",
    },
    "reason.stable": {"ar": "الطلب المتوقع مستقر", "en": "Expected demand is steady"},
    "reason.rise": {
        "ar": "ارتفاع الطلب المتوقع بنسبة {pct:.1f}%",
        "en": "Expected demand up {pct:.1f}%",
    },
    "reason.fall": {
        "ar": "انخفاض الطلب المتوقع بنسبة {pct:.1f}%",
        "en": "Expected demand down {pct:.1f}%",
    },
    "reason.stock_deducted": {
        "ar": "بعد خصم {units:,.0f} وحدة متاحة في المخزون",
        "en": "after deducting {units:,.0f} units available in stock",
    },
    "reason.model": {"ar": "نموذج التنبؤ: {name}", "en": "Forecast model: {name}"},
    "reason.historical_error": {
        "ar": "خطأ تاريخي {pct:.0f}%",
        "en": "historical error {pct:.0f}%",
    },
    "reason.unevaluated": {
        "ar": "لم يُقيَّم النموذج (بيانات غير كافية للاختبار)",
        "en": "model not scored (not enough data to test on)",
    },
    "reason.missing_factors": {
        "ar": "عوامل غير محسوبة: {count} من 5",
        "en": "{count} of 5 factors not computed",
    },
    "reason.borrowed": {
        "ar": ":material/warning: مُستعار بالكامل من «{source}» — لا تاريخ مبيعات لهذا المنتج",
        "en": ":material/warning: Entirely borrowed from \"{source}\" — this product has no sales history",
    },

    # ---- الاتجاه (من models/statistics.py) ----

    # ---- الرسوم والجداول ----
    "chart.history_of": {
        "ar": "التاريخ الفعلي - {product}",
        "en": "Actual history - {product}",
    },
    "chart.outliers": {"ar": "نقاط شاذة", "en": "Outliers"},
    "chart.performance_comparison": {"ar": "مقارنة الأداء", "en": "Performance comparison"},
    "table.change": {"ar": "التغير عن السابق", "en": "Change vs previous"},
    "table.change_pct": {"ar": "نسبة التغير", "en": "Change %"},
    "table.cumulative": {"ar": "التغير التراكمي", "en": "Cumulative"},

    # ---- تحذيرات الرفع ----
    "warn.duplicate_rows": {
        "ar": "{count} صفاً مكرّراً (منتج+شهر) — جُمعت كمياتها.",
        "en": "{count} duplicate rows (product+month) — their quantities were summed.",
    },
    "warn.stock_duplicate_rows": {
        "ar": "{count} صفاً مكرّراً لنفس المنتج — جُمع مخزونها (مستودعات "
              "متعددة، غالباً).",
        "en": "{count} duplicate rows for the same product — their stock was "
              "summed (likely multiple warehouses).",
    },
    "warn.dropped_columns": {
        "ar": "{count} عموداً لم يُفهَم كتاريخ فأُهمل: {names}",
        "en": "{count} columns were not understood as a date and were ignored: {names}",
    },
    "warn.timeline_gaps": {
        "ar": "فجوات في التسلسل الزمني: {found} فترة موجودة من {expected} "
              "بين {start} و{end}. الفترات الناقصة ليست أصفاراً — هي غياب "
              "بيانات، والموسمية المحسوبة عليها غير دقيقة.",
        "en": "Gaps in the timeline: {found} periods present out of {expected} "
              "between {start} and {end}. Missing periods are not zeros — they are "
              "absent data, and seasonality computed over them is unreliable.",
    },
    "warn.non_numeric": {
        "ar": "{count} خلية غير رقمية عوملت كصفر.",
        "en": "{count} non-numeric cells were treated as zero.",
    },
    "warn.negatives": {
        "ar": "{count} قيمة سالبة (مرتجعات؟) — رُفعت إلى صفر. "
              "المحرّكات تتعامل مع الطلب لا صافي الحركة.",
        "en": "{count} negative values (returns?) — clipped to zero. "
              "The engines model demand, not net movement.",
    },
    "warn.dead_products": {
        "ar": "{count} منتجاً بلا أي مبيعات — لا ينطبق عليها نموذج، "
              "وستُرفض صراحةً.",
        "en": "{count} products with no sales at all — no model applies to them, "
              "and they will be rejected explicitly.",
    },
    # -------------------------------------------------------------------
    # خطة الشراء — لمدير المشتريات: كم يشتري من كل منتج لتغطية أفق يختاره
    # -------------------------------------------------------------------
    "nav.purchase_plan": {"ar": "خطة الشراء", "en": "Purchase Plan"},
    "pplan.title": {"ar": ":material/shopping_cart: خطة الشراء", "en": ":material/shopping_cart: Purchase Plan"},
    "pplan.subtitle": {
        "ar": "لكل منتج: كمية الشراء الموصى بها لتغطية عدد {unit} الذي "
              "تحدّده أدناه — قابلة للتصدير Excel مباشرة.",
        "en": "Per product: the recommended purchase quantity to cover "
              "the number of {unit} you set below — exportable to Excel "
              "directly.",
    },
    "pplan.header": {"ar": "إعداد الخطة", "en": "Plan setup"},
    "pplan.horizon_label": {
        "ar": "عدد {unit} المراد تغطيتها", "en": "{unit} to cover",
    },
    "pplan.horizon_help": {
        "ar": "أفق واحد يُطبَّق على كل المنتجات — الكمية الناتجة لكل منتج "
              "تختلف بحسب طلبه المتوقَّع، لا الأفق نفسه.",
        "en": "One horizon applied to every product — the resulting "
              "quantity differs per product based on its own forecast, "
              "not the horizon itself.",
    },
    "pplan.lead_time_label": {
        "ar": "مهلة التوريد النمطية (أيام) — اختياري",
        "en": "Typical supplier lead time (days) — optional",
    },
    "pplan.lead_time_help": {
        "ar": "0 يعني غير معروفة. رقم واحد يُطبَّق على كل المنتجات — تقدير "
              "أولوية تقريبي، لا نظام نقطة إعادة طلب حقيقي (يحتاج مهلة "
              "خاصة بكل مورّد وتباينها، غير متوفرة بعد).",
        "en": "0 means unknown. One number applied to every product — a "
              "rough priority estimate, not a real reorder-point system "
              "(that needs per-supplier lead time and its variability, "
              "not available yet).",
    },
    "pplan.compute": {"ar": "احسب خطة الشراء", "en": "Compute purchase plan"},
    "pplan.empty": {
        "ar": "اضبط عدد {unit} واضغط \"احسب خطة الشراء\" من الشريط الجانبي.",
        "en": "Set the {unit} to cover and click \"Compute purchase plan\" "
              "in the sidebar.",
    },
    "pplan.stale_warning": {
        "ar": "البيانات تغيّرت منذ آخر حساب — النتائج أدناه قد لا تطابق "
              "الملف الحالي. اضغط \"احسب خطة الشراء\" لتحديثها.",
        "en": "Data changed since the last computation — results below "
              "may not match the current file. Click \"Compute purchase "
              "plan\" to refresh them.",
    },
    "pplan.kpi_assessed": {"ar": "منتجات مُقيَّمة", "en": "Products assessed"},
    "pplan.kpi_to_order": {"ar": "تحتاج شراءً", "en": "Need purchasing"},
    "pplan.kpi_low_confidence": {"ar": "بيانات قليلة جداً", "en": "Very little data"},
    "pplan.kpi_total_qty": {"ar": "إجمالي الكمية المطلوبة", "en": "Total quantity needed"},
    "pplan.no_stock_note": {
        "ar": "لم يُرفَع ملف مخزون — الكميات أعلاه هي الطلب المتوقَّع "
              "بالكامل بلا خصم أي مخزون حالي.",
        "en": "No stock file uploaded — quantities above are the full "
              "expected demand with no current stock deducted.",
    },
    "pplan.orders_title": {"ar": "أوامر الشراء", "en": "Purchase orders"},
    "pplan.nothing_to_order": {
        "ar": "لا منتج يحتاج شراءً بالكمية الحالية — كل الطلب المتوقَّع "
              "مغطّى بالمخزون، أو المنتجات المتبقية متوقّفة/راكدة (انظر "
              "القسم المستبعد أدناه).",
        "en": "No product needs purchasing at current stock — either "
              "demand is fully covered, or the remaining products are "
              "dormant/discontinued (see the excluded section below).",
    },
    "pplan.download_excel": {"ar": "⬇️ تنزيل ملف Excel", "en": "⬇️ Download Excel file"},
    "pplan.excluded_title": {
        "ar": "منتجات مستبعدة من أمر الشراء ({count})",
        "en": "Products excluded from the purchase order ({count})",
    },
    "pplan.excluded_help": {
        "ar": "كميتها المحسوبة أقل من نصف وحدة — غالباً متوقّفة عن البيع أو "
              "راكدة. موجودة هنا وفي ملف Excel (ورقة منفصلة) للشفافية، لا "
              "محذوفة بصمت.",
        "en": "Their computed quantity is under half a unit — usually "
              "discontinued or dormant. Shown here and in the Excel file "
              "(separate sheet) for transparency, not silently dropped.",
    },
    "pplan.skipped_title": {
        "ar": "منتجات تعذّر تقييمها كلياً ({count})",
        "en": "Products that couldn't be evaluated at all ({count})",
    },
    "pplan.col_stock": {"ar": "المخزون الحالي", "en": "Current stock"},
    "pplan.col_class": {"ar": "تصنيف الطلب", "en": "Demand class"},
    "pplan.col_note": {"ar": "ملاحظة", "en": "Note"},
    "pplan.col_reason": {"ar": "السبب", "en": "Reason"},
    "pplan.col_urgency": {"ar": "الأولوية", "en": "Priority"},
    "pplan.col_price": {"ar": "سعر الوحدة", "en": "Unit price"},
    "pplan.col_cost": {"ar": "التكلفة التقديرية", "en": "Estimated cost"},
    "urgency.urgent": {"ar": "🔴 اطلب الآن", "en": "🔴 Order now"},
    "urgency.can_wait": {"ar": "🟢 يمكن الانتظار", "en": "🟢 Can wait"},
    "pplan.kpi_total_cost": {
        "ar": "الإنفاق التقديري: {total:,.0f} (لـ {priced} من {total_lines} منتجاً بسعر معروف)",
        "en": "Estimated spend: {total:,.0f} ({priced} of {total_lines} products with a known price)",
    },
    "pplan.sheet_orders": {"ar": "أوامر الشراء", "en": "Purchase Orders"},
    "pplan.sheet_excluded": {"ar": "مستبعد", "en": "Excluded"},
    "pplan.sheet_skipped": {"ar": "بلا تقييم", "en": "Not Evaluated"},
    "note.cold_start": {
        "ar": "⚠️ منتج جديد جداً (3 أشهر فعلية أو أقل) — الكمية تقدير لا تنبؤ",
        "en": "⚠️ Very new product (3 or fewer active months) — a rough "
              "estimate, not a real forecast",
    },
    "note.recently_dormant": {
        "ar": "⚠️ لا بيع منذ 12 شهراً أو أكثر — راجع قبل الشراء",
        "en": "⚠️ No sales in 12+ months — review before purchasing",
    },
}
