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


def format_month(label: str) -> str:
    """إعادة صياغة تسمية شهر باللغة الحالية.

    ما لا يُفهَم يُترك كما هو: تسمية مخصّصة من ملف المستخدم ("W1-2024")
    ليست خطأً يُصحَّح، بل بياناته.
    """
    from services.ingest import parse_month_label

    parsed = parse_month_label(label)
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
        "ar": "⚠️ تعذّر تحميل البيانات: {detail}",
        "en": "⚠️ Could not load data: {detail}",
    },
    "common.product": {"ar": "المنتج", "en": "Product"},
    "common.month": {"ar": "الشهر", "en": "Month"},
    "common.quantity": {"ar": "الكمية", "en": "Quantity"},
    "common.risk": {"ar": "الخطورة", "en": "Risk"},
    "common.level": {"ar": "المستوى", "en": "Level"},
    "common.model": {"ar": "النموذج", "en": "Model"},
    "common.confidence": {"ar": "ثقة التقييم", "en": "Assessment confidence"},
    "common.wape": {"ar": "دقّة WAPE", "en": "WAPE accuracy"},
    "common.demand_change": {"ar": "تغيّر الطلب %", "en": "Demand change %"},
    "common.recommended_qty": {"ar": "الكمية الموصى بها", "en": "Recommended qty"},
    "common.duration_ms": {"ar": "زمن (ms)", "en": "Time (ms)"},
    "common.compute": {"ar": "الحساب", "en": "Compute"},
    "common.all_nine_models": {"ar": "كل النماذج التسعة", "en": "All nine models"},
    "common.all_nine_help": {
        "ar": "أدقّ، لكن دقائق على كتالوج كامل بدل ثانية واحدة.",
        "en": "More accurate, but minutes for a full catalogue instead of one second.",
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
    "nav.planning": {"ar": "تخطيط الإنتاج", "en": "Production Planning"},
    "nav.intelligence": {"ar": "ذكاء المنتج", "en": "Product Intelligence"},
    "nav.advanced": {"ar": "التحليل المتقدّم", "en": "Advanced Analytics"},

    # ---- البيانات والرفع ----
    "data.header": {"ar": "📁 البيانات", "en": "📁 Data"},
    "data.your_file": {
        "ar": "ملفك: **{products}** منتج × **{months}** شهر",
        "en": "Your file: **{products}** products × **{months}** months",
    },
    "data.notes": {
        "ar": "⚠️ ملاحظات على الملف ({count})",
        "en": "⚠️ Notes on your file ({count})",
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
        "ar": "🔒 ملفك يُحلَّل في الذاكرة ولا يُحفَظ على الخادم. "
              "يختفي بإغلاق التبويب، ولا يراه زائر آخر.",
        "en": "🔒 Your file is analysed in memory and never written to the server. "
              "It disappears when you close the tab, and no other visitor sees it.",
    },
    "data.privacy_local": {
        "ar": "🔒 ملفك في ذاكرة الجلسة ولا يُكتب في قاعدة البيانات. "
              "يختفي بإعادة التشغيل.",
        "en": "🔒 Your file lives in session memory and is never written to the database. "
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
        "ar": "🔗 ربط الأعمدة يدوياً",
        "en": "🔗 Map columns manually",
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

    # ---- أخطاء الرفع (من services/ingest.py عبر code) ----
    "error.unreadable_file": {
        "ar": "تعذّرت قراءة الملف — تأكّد أنه CSV أو Excel صالح.",
        "en": "Could not read the file — make sure it is a valid CSV or Excel file.",
    },
    "error.empty_file": {"ar": "الملف فارغ.", "en": "The file is empty."},
    "error.no_months": {
        "ar": "لم يُفهَم أي عمود كشهر. الأشكال المقبولة: "
              "'يناير 2023'، 'Jan 2023'، '2023-01'.",
        "en": "No column was understood as a month. Accepted formats: "
              "'Jan 2023', 'January 2023', '2023-01'.",
    },
    "error.too_few_months": {
        "ar": "{months} شهراً فقط — الحد الأدنى {minimum}.",
        "en": "Only {months} months — the minimum is {minimum}.",
    },
    "error.unsupported_granularity": {
        "ar": "بياناتك **{granularity}** — والمدعوم اليوم **شهري** فقط.\n\n"
              "لا نقبلها ونتظاهر: معاملتها كأشهر تجعل النظام يبحث عن دورة "
              "سنوية كل 12 {unit} ويُنتج موسمية خاطئة تبدو صحيحة. الرفض "
              "أصدق من رقم لا يُعتمد عليه.\n\n"
              "جمّع بياناتك شهرياً في نظامك ثم صدّرها — أو انتظر الدعم "
              "(البند الأول في خارطة الطريق).",
        "en": "Your data is **{granularity}** — only **monthly** is supported "
              "today.\n\nWe will not accept it and pretend: treating it as "
              "monthly makes the system hunt for a yearly cycle every 12 {unit} "
              "and produce seasonality that is wrong but looks right. A refusal "
              "is more honest than a number you cannot rely on.\n\nAggregate to "
              "months in your ERP and re-export — or wait for support (first "
              "item on the roadmap).",
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
    "exec.title": {"ar": "📊 النظرة التنفيذية", "en": "📊 Executive Overview"},
    "exec.computing": {"ar": "جارٍ الحساب...", "en": "Computing..."},
    "exec.recompute": {"ar": "🔄 حساب الكتالوج", "en": "🔄 Compute catalogue"},
    "exec.ephemeral_user": {
        "ar": "🔒 محسوب في الذاكرة ولا يُحفَظ — بياناتك ملكك.",
        "en": "🔒 Computed in memory, never stored — your data is yours.",
    },
    "exec.ephemeral_hosted": {
        "ar": "🔒 محسوب في الذاكرة ولا يُحفَظ — الوضع المستضاف.",
        "en": "🔒 Computed in memory, never stored — hosted mode.",
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
        "ar": "أقل من {threshold} وحدة متوقَّعة الشهر القادم — لا قرار إنتاج. "
              "خطورتها عالية بسبب تاريخ متذبذب: معلومة تستحق النظر (منتج "
              "يموت؟) لا إجراءً. فُصلت كي لا تزاحم ما يحتاج قراراً فعلياً.",
        "en": "Fewer than {threshold} units expected next month — no production "
              "decision. High risk from a volatile history: worth noticing (a "
              "product dying?) but not an action. Separated so it does not crowd "
              "out what actually needs deciding.",
    },
    "exec.fva_summary": {
        "ar": "📐 على {total} منتجاً بمقارنة صالحة: النموذج المختار تفوّق على "
              "التكرار الساذج (Naive) في {beat} منها ({pct:.0f}%). الباقي — "
              "الساذج كافٍ، ولا تعقيد اشترى شيئاً.",
        "en": "📐 Across {total} products with a valid comparison: the chosen "
              "model beat the naive baseline in {beat} of them ({pct:.0f}%). "
              "For the rest, naive was enough — complexity bought nothing.",
    },
    "exec.inventory_caveat": {
        "ar": "⚠️ عامل نفاد المخزون غير محسوب — جدول inventory فارغ حتى "
              "Phase 5. لذا ثقة التقييم 80% (4 عوامل من 5) لكل المنتجات.",
        "en": "⚠️ Stock-depletion risk is not computed — the inventory table is "
              "empty until Phase 5. That is why every product shows 80% "
              "confidence (4 factors of 5).",
    },

    # ---- التنبؤ ----
    "fc.title": {"ar": "🔮 التنبؤ", "en": "🔮 Forecasting"},
    "fc.subtitle": {
        "ar": "يُشغّل كل النماذج المنطبقة، يقيّمها على بيانات لم ترَها، "
              "ويختار الأفضل بالأدلة.",
        "en": "Runs every applicable model, scores each on data it never saw, "
              "and picks the winner on evidence.",
    },
    "fc.settings": {"ar": "إعدادات التنبؤ", "en": "Forecast settings"},
    "fc.horizon": {"ar": "أفق التنبؤ (أشهر)", "en": "Forecast horizon (months)"},
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
    "fc.next_month": {"ar": "تنبؤ الشهر القادم", "en": "Next month forecast"},
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
              "يستهلك إجمالي الأفق لا دقة كل شهر.",
        "en": "Metric: **cumulative error** — an intermittent series, and the "
              "production decision consumes the horizon total, not per-month "
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
        "ar": "**لم يُقيَّم أي نموذج.** السلسلة ({nonzero} شهراً بمبيعات من "
              "{total}) أقصر من أن تُقسَّم إلى تدريب واختبار.\n\nلذا اختار "
              "المحرك **{model}** بقاعدته المعلنة: بلا دليل على أن التعقيد "
              "يفيد، يفوز الأبسط. الرقم أعلاه تنبؤ حقيقي، لكن **بلا مقياس "
              "دقة يسنده** — تعامل معه بحذر.",
        "en": "**No model could be scored.** The series ({nonzero} selling months "
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

    # ---- تخطيط الإنتاج ----
    "plan.title": {"ar": "🏭 تخطيط الإنتاج", "en": "🏭 Production Planning"},
    "plan.subtitle": {
        "ar": "التوصية اقتراح النظام؛ الخطة قرارك. الفصل بينهما يسمح بقياس "
              "جودة التوصيات لاحقاً.",
        "en": "The recommendation is the system's suggestion; the plan is your "
              "decision. Keeping them apart lets you measure the recommendations "
              "later.",
    },
    "plan.local_only": {
        "ar": "**التخطيط متاح في الوضع المحلي فقط.** {reason} — والخطط تحتاج "
              "تخزيناً دائماً ليكون لها معنى (قياس المخطَّط مقابل الفعلي عبر "
              "الأشهر).\n\nاستنسخ المستودع وشغّله محلياً لاستخدام هذه الصفحة:",
        "en": "**Planning works in local mode only.** {reason} — and plans need "
              "durable storage to mean anything (comparing planned against actual "
              "across months).\n\nClone the repo and run it locally to use this "
              "page:",
    },
    "plan.reason_user_data": {
        "ar": "بياناتك المرفوعة تعيش في جلستك ولا تُكتب في قاعدة البيانات",
        "en": "your uploaded data lives in your session and is never written to "
              "the database",
    },
    "plan.reason_hosted": {
        "ar": "الوضع المستضاف لا يحفظ شيئاً على الخادم",
        "en": "hosted mode stores nothing on the server",
    },
    "plan.local_only_note": {
        "ar": "التنبؤ والخطورة وذكاء المنتج تعمل كاملةً على بياناتك هنا — "
              "التخزين وحده هو المعطَّل.",
        "en": "Forecasting, risk and product intelligence all work fully on your "
              "data here — only storage is disabled.",
    },
    "plan.inventory_warning": {
        "ar": "**الكميات لا تخصم المخزون** — جدول `inventory` فارغ حتى Phase 5. "
              "المعروض هو الطلب المتوقَّع كاملاً، لا الفجوة بينه وبين ما لديك.",
        "en": "**Quantities do not net off inventory** — the `inventory` table is "
              "empty until Phase 5. What you see is full expected demand, not the "
              "gap between it and your stock.",
    },
    "plan.create": {"ar": "إنشاء خطة", "en": "Create a plan"},
    "plan.system_suggests": {
        "ar": "توصية النظام: **{quantity:,}** — {reason}",
        "en": "System suggests: **{quantity:,}** — {reason}",
    },
    "plan.no_recommendation": {
        "ar": "لا توصية محفوظة لهذا المنتج. شغّل الحساب من **النظرة التنفيذية**.",
        "en": "No stored recommendation for this product. Run the compute from "
              "**Executive**.",
    },
    "plan.planned_qty": {"ar": "الكمية المخطَّطة", "en": "Planned quantity"},
    "plan.status": {"ar": "الحالة", "en": "Status"},
    "plan.notes": {"ar": "ملاحظات (اختياري)", "en": "Notes (optional)"},
    "plan.save": {"ar": "حفظ الخطة", "en": "Save plan"},
    "plan.overridden": {
        "ar": "خالفت التوصية ({suggested:,} → {actual:,.0f}). الفارق مسجَّل — "
              "وهو ما سيقيس جودة التوصيات لاحقاً.",
        "en": "You overrode the recommendation ({suggested:,} → {actual:,.0f}). "
              "The gap is recorded — that is what will measure recommendation "
              "quality later.",
    },
    "plan.saved": {
        "ar": "حُفظت خطة {product} لشهر {month}.",
        "en": "Saved the plan for {product}, {month}.",
    },
    "plan.existing": {"ar": "الخطط المسجَّلة", "en": "Recorded plans"},
    "plan.none_yet": {"ar": "لا خطط بعد.", "en": "No plans yet."},
    "plan.planned": {"ar": "المخطَّط", "en": "Planned"},
    "plan.actual": {"ar": "الفعلي", "en": "Actual"},
    "plan.notes_column": {"ar": "ملاحظات", "en": "Notes"},
    "plan.updated": {"ar": "آخر تحديث", "en": "Last updated"},
    "status.draft": {"ar": "مسودّة", "en": "Draft"},
    "status.approved": {"ar": "معتمدة", "en": "Approved"},
    "status.in_progress": {"ar": "قيد التنفيذ", "en": "In progress"},
    "status.completed": {"ar": "مكتملة", "en": "Completed"},
    "status.cancelled": {"ar": "ملغاة", "en": "Cancelled"},

    # ---- ذكاء المنتج ----
    "pi.title": {"ar": "🧠 ذكاء المنتج", "en": "🧠 Product Intelligence"},
    "pi.classification": {"ar": "تصنيف الطلب", "en": "Demand classification"},
    "pi.class": {"ar": "التصنيف", "en": "Class"},
    "pi.adi_help": {
        "ar": "متوسط الفترة بين الطلبات. 1.0 = كل شهر.",
        "en": "Average interval between demands. 1.0 = every month.",
    },
    "pi.cv2_help": {
        "ar": "تقلب أحجام الطلب غير الصفري.",
        "en": "Volatility of non-zero demand sizes.",
    },
    "pi.selling_months": {"ar": "أشهر بمبيعات", "en": "Months with sales"},
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
        "ar": "🔒 سجل النماذج التاريخي متاح في الوضع المحلي فقط — بياناتك لا "
              "تُحفَظ. كل ما فوق محسوب لجلستك الآن.",
        "en": "🔒 Historical model records are local-mode only — your data is not "
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
        "ar": "🔮 نظام تحليل وتنبؤ أوامر التصنيع – الإصدار الاحترافي",
        "en": "🔮 Advanced Analytics",
    },
    "adv.notice": {
        "ar": "هذه الصفحة تُشغّل **ETS** دائماً — ترتيبه الثامن من تسعة على "
              "هذا الكتالوج. لاختيار النموذج بالأدلة استخدم صفحة **التنبؤ**. "
              "تبقى هنا لتحليلاتها الإحصائية (الارتباط، التوزيع، الموسمية).",
        "en": "This page always runs **ETS** — which ranks 8th of 9 on this "
              "catalogue. For evidence-based model selection use **Forecasting**. "
              "It stays for its statistical analyses (correlation, distribution, "
              "seasonality).",
    },

    # ---- الشريط الجانبي القديم (التحليل المتقدّم) ----
    "old.control_panel": {"ar": "🎛️ لوحة التحكم", "en": "🎛️ Controls"},
    "old.select_products": {
        "ar": "اختر المنتج (يمكن اختيار عدة)",
        "en": "Select products (multiple allowed)",
    },
    "old.pick_one": {
        "ar": "الرجاء اختيار منتج واحد على الأقل",
        "en": "Please select at least one product",
    },
    "old.from_month": {"ar": "من شهر", "en": "From month"},
    "old.to_month": {"ar": "إلى شهر", "en": "To month"},
    "old.bad_range": {
        "ar": "تاريخ البداية يجب أن يكون قبل النهاية",
        "en": "The start month must come before the end month",
    },
    "old.forecast_settings": {"ar": "🔮 إعدادات التنبؤ", "en": "🔮 Forecast settings"},
    "old.forecast_months": {"ar": "عدد الأشهر للتنبؤ", "en": "Months to forecast"},
    "old.show_confidence": {"ar": "عرض فترات الثقة", "en": "Show confidence intervals"},
    "old.forecast_model": {"ar": "نموذج التنبؤ", "en": "Forecast model"},
    # قيم لا تسميات — الكود يقارن بالرمز، والتسمية تُشتقّ منه.
    # قبل هذا كان dashboard.py يقارن بالنص الحرفي "SARIMA (إذا توفر)"،
    # فترجمة التسمية كانت ستكسر المقارنة بصمت: SARIMA لا يعمل، بلا خطأ.
    "model.ets": {"ar": "ETS (التنعيم الأسي)", "en": "ETS (exponential smoothing)"},
    "model.sarima": {"ar": "SARIMA (إذا توفر)", "en": "SARIMA (if available)"},
    "old.extra_analyses": {"ar": "📊 تحليلات إضافية", "en": "📊 Extra analyses"},
    "old.trend": {"ar": "تحليل الاتجاه", "en": "Trend analysis"},
    "old.seasonal": {"ar": "التحليل الموسمي", "en": "Seasonal analysis"},
    "old.correlation": {"ar": "مصفوفة الارتباط بين المنتجات", "en": "Product correlation matrix"},
    "old.distribution": {"ar": "تحليل التوزيع الإحصائي", "en": "Statistical distribution"},
    "old.outliers": {"ar": "كشف النقاط الشاذة", "en": "Outlier detection"},
    "old.run": {"ar": "🔄 تشغيل التحليل المتقدم", "en": "🔄 Run advanced analysis"},

    # ---- لوحة التحليل المتقدّم ----
    "old.product_analysis": {
        "ar": "📊 تحليل المنتج: {product}",
        "en": "📊 Product analysis: {product}",
    },
    "old.total": {"ar": "📦 الإجمالي", "en": "📦 Total"},
    "old.average": {"ar": "📈 المتوسط", "en": "📈 Average"},
    "old.max": {"ar": "⬆ الأعلى", "en": "⬆ Highest"},
    "old.min_nonzero": {"ar": "⬇ الأدنى (غير صفري)", "en": "⬇ Lowest (non-zero)"},
    "old.std": {"ar": "📊 الانحراف المعياري", "en": "📊 Std deviation"},
    "old.median": {"ar": "📌 الوسيط", "en": "📌 Median"},
    "old.nonzero_months": {"ar": "📅 أشهر (>0)", "en": "📅 Months (>0)"},
    "old.cv": {"ar": "📉 معامل الاختلاف", "en": "📉 Coefficient of variation"},
    "old.last_value": {"ar": "🔮 آخر قيمة", "en": "🔮 Last value"},
    "old.first_forecast": {
        "ar": "📈 قيمة التنبؤ (أول شهر)",
        "en": "📈 Forecast (first month)",
    },
    "old.accuracy_metrics": {
        "ar": "📈 مقاييس دقة التنبؤ (ETS)",
        "en": "📈 Forecast accuracy metrics (ETS)",
    },
    "old.trend_analysis": {"ar": "📈 تحليل الاتجاه", "en": "📈 Trend analysis"},
    "old.direction": {"ar": "الاتجاه", "en": "Direction"},
    "old.slope": {"ar": "الميل (لكل شهر)", "en": "Slope (per month)"},
    "old.r_squared": {"ar": "R² (قوة النموذج)", "en": "R² (fit strength)"},
    "old.p_value": {"ar": "قيمة p (الدلالة)", "en": "p-value (significance)"},
    "old.outliers_found": {
        "ar": "تم اكتشاف {count} نقطة شاذة (أشهر: {months})",
        "en": "{count} outliers detected (months: {months})",
    },
    "old.main_chart": {"ar": "📈 الاتجاه الفعلي والتنبؤ", "en": "📈 Actual trend and forecast"},
    "old.correlation_title": {"ar": "🔗 مصفوفة الارتباط", "en": "🔗 Correlation matrix"},
    "old.seasonal_title": {"ar": "📅 التحليل الموسمي (حسب الربع)", "en": "📅 Seasonal analysis (by quarter)"},
    "old.distribution_title": {"ar": "📊 تحليل التوزيع الإحصائي", "en": "📊 Statistical distribution"},
    "old.details_table": {"ar": "📋 البيانات التفصيلية مع التغيرات", "en": "📋 Detailed data with changes"},
    "old.export": {"ar": "⬇️ تصدير التقارير", "en": "⬇️ Export reports"},
    "old.download_csv": {"ar": "⬇ تحميل CSV (البيانات الفعلية)", "en": "⬇ Download CSV (actual data)"},
    "old.download_excel": {"ar": "⬇ تحميل Excel (مع التنبؤ)", "en": "⬇ Download Excel (with forecast)"},
    "old.no_outliers": {"ar": "✅ لم يتم اكتشاف نقاط شاذة", "en": "✅ No outliers detected"},
    "old.comparison_selected": {
        "ar": "📊 مقارنة المنتجات المختارة", "en": "📊 Selected product comparison",
    },
    "old.correlation_products": {
        "ar": "📊 مصفوفة الارتباط بين المنتجات", "en": "📊 Product correlation matrix",
    },
    "old.footer": {
        "ar": "🔮 نظام تحليل وتنبؤ متقدم – يعمل بنماذج ETS، SARIMA، والانحدار الخطي",
        "en": "🔮 Advanced analysis and forecasting — powered by ETS, SARIMA and linear regression",
    },
    "old.analysed_range": {
        "ar": "📅 تم تحليل البيانات من {start} إلى {end} (عدد الأشهر: {count})",
        "en": "📅 Analysed data from {start} to {end} ({count} months)",
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

    # ---- الاتجاه (من models/statistics.py) ----
    "trend.up": {"ar": "📈 صاعد", "en": "📈 Rising"},
    "trend.down": {"ar": "📉 هابط", "en": "📉 Falling"},
    "trend.flat": {"ar": "➡️ مستقر", "en": "➡️ Flat"},

    # ---- الرسوم والجداول ----
    "chart.series": {"ar": "النوع", "en": "Series"},
    "chart.ets_forecast": {"ar": "تنبؤ ETS", "en": "ETS forecast"},
    "chart.sarima_forecast": {"ar": "تنبؤ SARIMA", "en": "SARIMA forecast"},
    "chart.trend_and_forecast": {
        "ar": "الاتجاه والتنبؤ - {product}",
        "en": "Trend and forecast - {product}",
    },
    "chart.outliers": {"ar": "نقاط شاذة", "en": "Outliers"},
    "chart.lower": {"ar": "حد أدنى 95%", "en": "Lower 95%"},
    "chart.monthly_comparison": {"ar": "مقارنة الأداء الشهري", "en": "Monthly performance comparison"},
    "chart.quarter": {"ar": "الربع", "en": "Quarter"},
    "chart.average": {"ar": "المتوسط", "en": "Average"},
    "chart.quarterly_average": {"ar": "متوسط الكمية حسب الربع", "en": "Average quantity by quarter"},
    "chart.q1": {"ar": "الربع 1", "en": "Q1"},
    "chart.q2": {"ar": "الربع 2", "en": "Q2"},
    "chart.q3": {"ar": "الربع 3", "en": "Q3"},
    "chart.q4": {"ar": "الربع 4", "en": "Q4"},
    "chart.histogram": {"ar": "مدرج تكراري", "en": "Histogram"},
    "chart.frequency": {"ar": "التكرار", "en": "Frequency"},
    "chart.boxplot": {"ar": "صندوق الحظائر (Boxplot)", "en": "Boxplot"},
    "chart.density": {"ar": "منحنى الكثافة", "en": "Density curve"},
    "table.change": {"ar": "التغير عن السابق", "en": "Change vs previous"},
    "table.change_pct": {"ar": "نسبة التغير", "en": "Change %"},
    "table.cumulative": {"ar": "التغير التراكمي", "en": "Cumulative"},

    # ---- تحذيرات الرفع ----
    "warn.duplicate_rows": {
        "ar": "{count} صفاً مكرّراً (منتج+شهر) — جُمعت كمياتها.",
        "en": "{count} duplicate rows (product+month) — their quantities were summed.",
    },
    "warn.dropped_columns": {
        "ar": "{count} عموداً لم يُفهَم كشهر فأُهمل: {names}",
        "en": "{count} columns were not understood as months and were ignored: {names}",
    },
    "warn.timeline_gaps": {
        "ar": "فجوات في التسلسل الزمني: {found} شهراً موجوداً من {expected} "
              "بين {start} و{end}. الأشهر الناقصة ليست أصفاراً — هي غياب "
              "بيانات، والموسمية المحسوبة عليها غير دقيقة.",
        "en": "Gaps in the timeline: {found} months present out of {expected} "
              "between {start} and {end}. Missing months are not zeros — they are "
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
}
