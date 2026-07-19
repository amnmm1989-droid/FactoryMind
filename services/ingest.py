# services/ingest.py
"""
قراءة بيانات المستخدم من CSV/Excel.

هذا الملف يحوّل المشروع من "أداة لبياناتنا" إلى "أداة لبيانات أي مصنع".
قبله لم يكن هناك أي مسار لإدخال بيانات: `data/data.json` مثبَّت في
config.py، ولا `file_uploader` في الكود كله.

يقبل الشكلين اللذين يُصدّرهما العالم الحقيقي:

    عريض (wide) — الأشيع، مخرج Excel/ERP المعتاد:
        المنتج   | يناير 2023 | فبراير 2023 | ...
        مضخة 50mm |    120     |     95      | ...

    طويل (long) — مخرج قواعد البيانات:
        المنتج    | الشهر       | الكمية
        مضخة 50mm | يناير 2023  | 120

القاعدة الحاكمة هنا كما في بقية المشروع: البيانات المشبوهة تُرفَض أو
يُحذَّر منها صراحةً، ولا تُصحَّح بصمت. ملف بعمود تاريخ غير مفهوم يجب أن
يقول ذلك — لا أن يُخمَّن ويُنتج موسمية على تقويم خاطئ.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

import config
from core.exceptions import DataValidationError

# أسماء الأشهر العربية — pandas لا يفهمها، وهي شكل بيانات هذا المشروع نفسه
ARABIC_MONTHS = {
    "يناير": 1, "كانون الثاني": 1,
    "فبراير": 2, "شباط": 2,
    "مارس": 3, "آذار": 3, "اذار": 3,
    "أبريل": 4, "ابريل": 4, "نيسان": 4,
    "مايو": 5, "أيار": 5, "ايار": 5,
    "يونيو": 6, "يونية": 6, "حزيران": 6,
    "يوليو": 7, "يولية": 7, "تموز": 7,
    "أغسطس": 8, "اغسطس": 8, "آب": 8, "اب": 8,
    "سبتمبر": 9, "أيلول": 9, "ايلول": 9,
    "أكتوبر": 10, "اكتوبر": 10, "تشرين الأول": 10,
    "نوفمبر": 11, "تشرين الثاني": 11,
    "ديسمبر": 12, "كانون الأول": 12,
}

# تلميحات أسماء الأعمدة في الشكل الطويل.
#
# "material" هو اسم العمود في تصديرة SAP — وكانت ترجمته "المادة" هنا منذ
# البداية بينما الأصل الإنجليزي منسيّ. فكان الشكل الطويل من SAP يسقط إلى
# _from_wide، فيحاول قراءة Period/Quantity كأشهر، ويردّ "لم يُفهَم أي عمود
# كشهر" — رسالة تُرسل المستخدم خلف مشكلة ليست مشكلته. (الشكل العريض من SAP
# كان يعمل دائماً: _from_wide لا يقرأ اسم العمود الأول أصلاً.)
# مقصورة على ما نعرفه: "material" اسم حقل SAP القياسي، و"part" شائع في
# تصديرات التصنيع. لا تُضاف لغة أو نظام بالتخمين — تلميح خاطئ يلتقط عموداً
# ليس المنتج، فيُنتج تحليلاً مقلوباً بصمت بدل خطأ صريح. أضِف عند ورود
# تصديرة حقيقية تُثبت الاسم.
PRODUCT_HINTS = (
    "product", "item", "sku",
    "material",   # SAP
    "part",       # شائع في تصديرات التصنيع
    "المنتج", "الصنف", "المادة",
)
MONTH_HINTS = ("month", "date", "period", "الشهر", "التاريخ", "الفترة")
QUANTITY_HINTS = ("quantity", "qty", "amount", "value", "sales", "الكمية", "العدد", "المبيعات")

# فئة/عائلة المنتج — عمود رابع اختياري، للتوفيق الهرمي (Bottom-Up) فقط.
# لا يشارك في تحديد الشكل طويل/عريض: ملف بلا هذا العمود يُقرأ بلا فئات،
# لا يُرفَض. غير مدعوم بعد في شاشة الربط اليدوي (ui/data_source.py) —
# اكتشاف تلقائي فقط، توسيعاً لاحقاً إن ثبتت الحاجة.
CATEGORY_HINTS = ("category", "family", "group", "التصنيف", "الفئة", "العائلة")

# عمود الكمية في ملف المخزون — تقاطع متعمَّد مع QUANTITY_HINTS: نفس
# الكلمات الشائعة ("quantity"، "qty") تسمّي عموداً مختلفاً كلياً هنا (رصيد
# آني لا مبيعات شهرية)، لكن الملفين لا يُقرآن معاً أبداً فلا لبس فعلي.
STOCK_HINTS = (
    "stock", "on hand", "on-hand", "balance", "available", "qty", "quantity",
    "المخزون", "الرصيد", "الكمية المتاحة", "الكمية الحالية",
)

# عمود سعر الوحدة — اختياري بالكامل في ملف المخزون، لخطة الشراء
# (services/decision_engine/purchase_plan.py) فقط: يحوّل كمية موصى بها
# إلى تكلفة تقديرية. غيابه لا يمنع رفع الملف — نفس مبدأ CATEGORY_HINTS:
# معلومة إضافية اختيارية، لا شرط.
PRICE_HINTS = ("price", "unit price", "unit cost", "cost", "السعر", "سعر الوحدة", "التكلفة")

MIN_MONTHS = 3  # أقل من ذلك لا يُنتج تنبؤاً ذا معنى بأي نموذج

# الأرقام العربية-الهندية: تصديرات ERP بواجهة عربية تكتب بها أحياناً.
_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# تجميع آلاف لا لبس فيه: مجموعات ثلاثية بعد الفاصلة الأولى، وكسر اختياري.
# "1,200" و"1,200.50" و"12,345,678" — نعم. "1,20" و"1,2345" — لا، فتُترك
# لـ to_numeric ترفضها بدل تخمين المعنى.
_THOUSANDS = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")

# فراغ يفصل الآلاف (شائع في تصديرات أوروبية): "1 200"، وبمسافة غير فاصلة.
_SPACED_THOUSANDS = re.compile(r"^-?\d{1,3}([   ]\d{3})+(\.\d+)?$")


def _clean_number(value):
    """تطبيع نصّ رقمي قبل التحويل — ما لا يُطبَّع يُترك ليُرفَض.

    ⚠️ يسدّ فقداً صامتاً للبيانات وجده اختبار ملفات غريبة، لا الاختبارات:
    خلية "1,200" نصّاً كانت تصير **صفراً**، لأن `to_numeric(errors=
    "coerce")` يُرجع NaN ثم `fillna(0.0)` يبتلعه. النتيجة أسوأ من الخطأ:

      قرأت الأداة   A = [0.0, 0.0, 950.0]
      وفي الملف     A = [1,200, 1,100, 950]

    والنمط هو الأخطر: الأرقام التي تتجاوز الألف وحدها هي التي تحمل فاصلة،
    فيُمحى **بالضبط** ما فوق الألف ويبقى ما دونه. منتج يبيع 1,200 شهرياً
    يُقرأ ميتاً، فتوصي الأداة بإنتاج صفر منه. ولا شيء يصرخ: تحذير
    non_numeric عامّ يقول "قيمتان" بلا اسم منتج ولا ذكرَ أنهما استُبدلتا
    بصفر.

    وفواصل الآلاف شائعة في تصديرات Excel من أنظمة ERP — أي أن هذا كان
    ينتظر أول ملف مصنع حقيقي.

    القاعدة محافِظة عمداً: تُزال الفاصلة فقط حين يكون التجميع ثلاثياً بلا
    لبس. "1,20" تبقى كما هي فتُرفَض بصوت، لأن معناها يختلف بين لغة وأخرى
    (1.20 أوروبياً، ولا شيء معرَّفاً عربياً) والتخمين هنا أسوأ من الرفض.
    """
    if not isinstance(value, str):
        return value
    text = value.strip().translate(_ARABIC_INDIC)
    if not text:
        return value
    if _THOUSANDS.match(text):
        return text.replace(",", "")
    if _SPACED_THOUSANDS.match(text):
        return re.sub(r"[   ]", "", text)
    return text


def to_numeric(data):
    """`pd.to_numeric` مسبوقاً بالتطبيع — المدخل الوحيد للأرقام هنا.

    مرَّ ملف المبيعات وملف المخزون بمسارين منفصلين لنفس التحويل، فكان
    العطل نفسه في كليهما. بابٌ واحد يمنع أن يُصلَح أحدهما دون الآخر.
    """
    return pd.to_numeric(data.map(_clean_number), errors="coerce")

# الحبيبة الزمنية: الفارق النمطي بالأيام -> الاسم. مُشتقّة من
# config.GRANULARITY_DAYS بالعكس — مصدر واحد للحقيقة، لا نسخة مستقلة قد
# تنحرف عنها.
#
# كل الحبيبات الخمس مقبولة الآن (راجع docs/ROADMAP.md — "الحبيبة الزمنية
# المرنة"، البند 1): الملف يُقرأ بحبيبته الفعلية بدل رفض ما ليس شهرياً.
GRANULARITY_BUCKETS = {days: name for name, days in config.GRANULARITY_DAYS.items()}
# افتراضي عند الغموض فقط (detect_granularity لا يجد يومين مختلفين ليقيس
# بينهما) — لا حبيبة "مدعومة" بمعنى الرفض؛ الخمس كلها مقبولة دوماً.
DEFAULT_GRANULARITY = "monthly"


@dataclass(frozen=True)
class Warning_:
    """تحذير كبيانات لا كنص.

    الخدمة تعرف *ما* حدث؛ الواجهة تعرف *بأي لغة* تقوله. خلطهما هنا كان
    سيثبّت العربية داخل طبقة لا علاقة لها بالعرض — ويجعل المستخدم
    الإنجليزي يقرأ تحذيرات عربية وسط واجهته.
    """

    code: str
    params: dict = field(default_factory=dict)


@dataclass
class Dataset:
    """بيانات جاهزة للمحرّكات + ما يجب أن يعرفه المستخدم عنها."""

    months: list[str]                      # التسميات كما يراها المستخدم
    products: dict[str, list[float]]
    start_date: date | None                # مشتقّ من الملف، لا مثبَّت
    # الحبيبة المكتشَفة فعلياً ("daily"/"weekly"/"monthly"/"quarterly"/
    # "yearly") — لا افتراض شهري صامت. راجع docs/ROADMAP.md بند 1.
    granularity: str = DEFAULT_GRANULARITY
    warnings: list[Warning_] = field(default_factory=list)
    # فئة كل منتج، إن وُجد عمود فئة في الملف (شكل طويل فقط، اكتشاف تلقائي).
    # {} لا تعني فشلاً — تعني أن الملف لا يحمل هذه المعلومة، وهذا شائع
    # ومتوقَّع. منتج غائب من هذا القاموس يُستبعد من التوفيق الهرمي لا
    # يُحتسب في فئة مخترعة (services/reconciliation.py).
    categories: dict[str, str] = field(default_factory=dict)

    @property
    def product_count(self) -> int:
        return len(self.products)

    @property
    def month_count(self) -> int:
        return len(self.months)


@dataclass
class StockSnapshot:
    """لقطة مخزون آنية — لا سلسلة زمنية. صفّ واحد لكل منتج، لا شهر.

    ملف مبيعات وملف مخزون شكلان مختلفان جوهرياً لا صدفة تسمية: الأول
    تاريخ (Dataset)، والثاني حالة الآن فقط (levels). دمجهما في نفس الكيان
    كان سيجعل "شهر" حقلاً بلا معنى في نصف الحالات.
    """

    levels: dict[str, float]              # {اسم المنتج: المخزون الحالي}
    warnings: list[Warning_] = field(default_factory=list)
    # {} لا تعني فشلاً — تعني أن الملف لا يحمل عمود سعر، وهذا متوقَّع؛
    # نفس مبدأ categories في Dataset. منتج غائب هنا يُستبعد من حساب
    # التكلفة في خطة الشراء لا يُحتسب بسعر صفر مخترَع.
    prices: dict[str, float] = field(default_factory=dict)


# تسميات الأسبوع والربع كما تُصدِّرها ERP (Odoo: "W1 2023"، "Q1 2023").
# pandas لا يفهم أياً منهما — كان الملف الأسبوعي والربعي يُرفَضان كلياً
# (كل الأعمدة غير مقروءة -> no_months) قبل هذا. نحوّلهما إلى تاريخ فعلي:
# الأسبوع إلى اثنين أسبوعه ISO، والربع إلى أول شهر فيه.
WEEK_LABEL = re.compile(r"^[Ww]\s?(\d{1,2})\s+(1[89]\d{2}|20\d{2})$")
QUARTER_LABEL = re.compile(r"^[Qq]\s?([1-4])\s+(1[89]\d{2}|20\d{2})$")


def parse_full_date(label: str) -> date | None:
    """تحويل تسمية إلى تاريخ **باليوم** — لا يُقصّ.

    الفارق عن parse_month_label جوهري وليس تفصيلاً: قصّ اليوم يجعل
    2025-01-06 و2025-01-13 و2025-01-20 كلها 2025-01-01، فتضيع الحبيبة
    الزمنية *قبل* أن تُقاس. الكشف يحتاج التواريخ كاملة.

    تسمية شهرية بلا يوم ("يناير 2023") تُرجع اليوم الأول — وهو الصحيح:
    البيانات الشهرية لا يوم لها. وكذلك "Q1 2023" -> أول الربع، و"W1 2023"
    -> اثنين الأسبوع، فتُقرأ ملفات ERP الأسبوعية والربعية بدل رفضها.
    """
    text = str(label).strip()
    if not text:
        return None

    # عربي: اسم الشهر + سنة (بلا يوم — بيانات شهرية بطبيعتها)
    for name, number in ARABIC_MONTHS.items():
        if name in text:
            year_match = re.search(r"(1[89]\d{2}|20\d{2})", text)
            if year_match:
                return date(int(year_match.group(1)), number, 1)
            return None

    # أسبوعي "W# YYYY": اثنين أسبوع ISO. رقم أسبوع لا وجود له في تلك السنة
    # (W53 في سنة من 52 أسبوعاً) يُعيد None فيُحذَف العمود بتحذير لا بانهيار.
    week_match = WEEK_LABEL.match(text)
    if week_match:
        week, year = int(week_match.group(1)), int(week_match.group(2))
        try:
            return date.fromisocalendar(year, week, 1)
        except ValueError:
            return None

    # ربعي "Q# YYYY": Q1->يناير، Q2->أبريل، Q3->يوليو، Q4->أكتوبر.
    quarter_match = QUARTER_LABEL.match(text)
    if quarter_match:
        quarter, year = int(quarter_match.group(1)), int(quarter_match.group(2))
        return date(year, (quarter - 1) * 3 + 1, 1)

    # الباقي: pandas أقدر على أشكال التاريخ الإنجليزية والرقمية
    try:
        parsed = pd.to_datetime(text, errors="raise", dayfirst=False)
        return date(parsed.year, parsed.month, parsed.day)
    except (ValueError, TypeError, pd.errors.ParserError):
        return None


def parse_month_label(label: str) -> date | None:
    """تحويل تسمية شهر إلى بداية شهرها. None إن تعذّر — لا تخمين.

    يفهم: "يناير 2023"، "Jan 2023"، "2023-01"، "01/2023"، "Jan-23"...
    ولا يفهم: "الشهر الأول"، "P1"، "أسبوع 3" — وتلك تُرجع None ليُحذَّر
    المستخدم بدل أن تُخمَّن.

    يُستخدم للترتيب والعرض. لقياس الحبيبة استخدم parse_full_date.
    """
    parsed = parse_full_date(label)
    return date(parsed.year, parsed.month, 1) if parsed else None


def detect_granularity(dates: list[date]) -> str | None:
    """استنتاج الحبيبة الزمنية. None حين لا تكفي التواريخ لقياسها.

    ## القاعدة الأولى: التسمية بلا يوم لا يمكن أن تكون أدق من شهر

    "يناير 2024" و"2024-01" و"Jan 2024" لا تحمل يوماً — فهي شهرية بحكم
    بنيتها، مهما تباعدت. هذا يحسم الحالة التي تُسقط أي كاشف يعتمد على
    الفوارق وحدها: بيانات شهرية بفجوات كبيرة (يناير، يونيو، ديسمبر)
    فوارقها 152 و183 يوماً، وأي تصنيف بالفوارق يسمّيها "ربعية" خطأً.

    والبيانات المتقطّعة — 84% من هذا الكتالوج — تُصدَّر بأشهر ناقصة
    كثيراً. الرفض الكاذب هنا عطل أيضاً، أعلى صوتاً فقط.

    ## القاعدة الثانية: مع يوم صريح، الفارق الأصغر هو الحبيبة

    الفجوات مضاعفات للحبيبة لا حبيبة أخرى: أسبوعي بفجوة فوارقه 7 و14
    و21 — والأصغر (7) هو الحقيقة. المتوسط والمنوال كلاهما يضلّل هنا.
    """
    unique = sorted(set(dates))
    if len(unique) < 2:
        return None

    # كلها في أول الشهر -> تسميات شهرية (أو أخشن). لا نميّز الربعي عنها:
    # التمييز يحتاج انتظاماً لا تعطيه ثلاث نقاط، وخطؤه يرفض بيانات صحيحة.
    # والعطل الذي نحرسه هو الأدقّ-من-شهري تحديداً.
    if all(d.day == 1 for d in unique):
        return "monthly"

    smallest_gap = min(
        (unique[i + 1] - unique[i]).days for i in range(len(unique) - 1)
    )
    return GRANULARITY_BUCKETS[
        min(GRANULARITY_BUCKETS, key=lambda b: abs(smallest_gap - b))
    ]


# سنة مجرّدة "2023" — لا شهر ولا يوم، فهي سنوية ببنيتها. مفصولة عن
# WEEK/QUARTER لأن تلك تحمل علامة صريحة (W/Q) بينما هذه أربعة أرقام فقط.
YEAR_LABEL = re.compile(r"^(1[89]\d{2}|20\d{2})$")


def detect_granularity_from_labels(labels: list[str]) -> str | None:
    """الحبيبة من *شكل التسمية* لا من فجوات التواريخ.

    التسمية أصدق من الفجوة حين تحمل علامة صريحة: "Q1 2023" ربعي يقيناً،
    و"2023" سنوي يقيناً، مهما بدت فجواتهما. وهذا يحسم عطلاً لا يقدر عليه
    detect_granularity وحده: الربعي والسنوي كلاهما يسقط على أول الشهر
    (اليوم = 1)، فكاشف الفجوات يسمّي كليهما "شهرياً" خطأً.

    يُرجع None حين لا تحمل التسميات علامة صريحة موحّدة (أشهر، تواريخ
    كاملة، أو خليط) — فيتولّى detect_granularity القياس بالفجوات.
    """
    stripped = [str(label).strip() for label in labels]
    non_empty = [label for label in stripped if label]
    if not non_empty:
        return None

    for pattern, granularity in (
        (WEEK_LABEL, "weekly"),
        (QUARTER_LABEL, "quarterly"),
        (YEAR_LABEL, "yearly"),
    ):
        if all(pattern.match(label) for label in non_empty):
            return granularity
    return None


def _read_file(content: bytes, filename: str) -> pd.DataFrame:
    name = filename.lower()
    try:
        if name.endswith((".xlsx", ".xls", ".xlsm")):
            return pd.read_excel(io.BytesIO(content))
        # utf-8-sig يلتهم الـ BOM الذي يضعه Excel ويُفسد اسم أول عمود
        return pd.read_csv(io.BytesIO(content), encoding="utf-8-sig")
    except Exception as exc:
        raise DataValidationError(
            f"تعذّرت قراءة الملف: {exc}",
            cause=exc,
            context={"code": "unreadable_file", "filename": filename},
        ) from exc


def _find_column(columns: list[str], hints: tuple[str, ...]) -> str | None:
    for column in columns:
        if any(hint in str(column).strip().lower() for hint in hints):
            return column
    return None


def _detect_layout(frame: pd.DataFrame) -> str:
    """طويل أم عريض؟

    الطويل يحتاج ثلاثة أعمدة معنونة (منتج/شهر/كمية). أي شيء آخر عريض:
    عمود أول للأسماء وبقية الأعمدة أشهر.
    """
    columns = [str(c) for c in frame.columns]
    has_long_shape = (
        _find_column(columns, PRODUCT_HINTS)
        and _find_column(columns, MONTH_HINTS)
        and _find_column(columns, QUANTITY_HINTS)
    )
    return "long" if has_long_shape else "wide"


def _from_long(
    frame: pd.DataFrame,
    product_column: str,
    month_column: str,
    quantity_column: str,
    category_column: str | None = None,
) -> tuple[pd.DataFrame, list[Warning_], dict[str, str]]:
    """محور (منتج × شهر) من ثلاثة أعمدة معلومة الاسم — تخميناً أو يدوياً.

    الأعمدة تصل جاهزة لا تُكتشَف هنا: parse_upload يمرّرها من _find_column
    (التخمين)، وparse_upload_with_mapping يمرّرها من اختيار المستخدم
    (شاشة الربط اليدوي). المحور نفسه لا يفرّق بين الحالتين — وهذا مقصود:
    خطأ في التخمين وخطأ في اختيار المستخدم يُعاملان بمعيار واحد.

    category_column اختياري بالكامل — لا يشارك في المحور، ولا يُرفَض
    غيابه. حين يوجد: أول قيمة غير فارغة لكل منتج تُؤخَذ فئته؛ صفوف لاحقة
    بفئة مختلفة لنفس المنتج (بيانات متضاربة) لا تُرفَض ولا تُدمَج — تُتجاهَل
    بصمت القيمة الأولى فقط أصحّ، فالفئة صفة شبه ثابتة للمنتج، لا قيمة شهرية.
    """
    warnings: list[Warning_] = []
    duplicates = int(frame.duplicated(subset=[product_column, month_column]).sum())
    if duplicates:
        # الجمع لا الأخذ الأول: صفّان لنفس المنتج/الشهر يعنيان طلبين
        warnings.append(Warning_("duplicate_rows", {"count": duplicates}))

    pivoted = frame.pivot_table(
        index=product_column, columns=month_column,
        values=quantity_column, aggfunc="sum", fill_value=0,
    )

    category_of: dict[str, str] = {}
    if category_column is not None:
        for product, category in zip(frame[product_column], frame[category_column]):
            key = str(product).strip()
            if key and key not in category_of and pd.notna(category):
                value = str(category).strip()
                if value:
                    category_of[key] = value

    return pivoted, warnings, category_of


def _from_wide(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[Warning_]]:
    if frame.shape[1] < 2:
        raise DataValidationError(
            "الملف يحتاج عمود أسماء وعمود شهر واحداً على الأقل",
            context={"code": "missing_columns", "columns": frame.shape[1]},
        )
    return frame.set_index(frame.columns[0]), []


def read_columns(content: bytes, filename: str) -> list[str]:
    """أعمدة الملف الفعلية — بلا تحليل. لشاشة ربط الأعمدة اليدوي حين يفشل
    التخمين: تعرض للمستخدم ما في ملفه فعلاً، لا قائمة تلميحات لا تعنيه.

    Raises:
        DataValidationError: نفس أخطاء _read_file (unreadable_file, empty_file).
    """
    frame = _read_file(content, filename)
    if frame.empty:
        raise DataValidationError(
            "الملف فارغ", context={"code": "empty_file", "filename": filename}
        )
    return [str(c) for c in frame.columns]


def guess_column(columns: list[str], role: str) -> str | None:
    """أفضل تخمين لعمود بدور معيّن — لتعبئة شاشة الربط اليدوي مسبقاً.

    role: "product" | "month" | "quantity" | "stock". يستخدم نفس تلميحات
    التخمين التلقائي (PRODUCT_HINTS إلخ) — تخمين أفضل من لا شيء، لكنه
    يبقى تخميناً يُعرض على المستخدم لا يُفرَض عليه؛ الشاشة تسمح بتغييره
    بنقرة.
    """
    hints = {
        "product": PRODUCT_HINTS,
        "month": MONTH_HINTS,
        "quantity": QUANTITY_HINTS,
        "stock": STOCK_HINTS,
    }[role]
    return _find_column(columns, hints)


def _expected_period_count(dates: list[date], granularity: str) -> int:
    """عدد الفترات المتوقَّع بين أول تاريخ وآخره، حسب الحبيبة المكتشَفة.

    الشهري وحده حساب تقويمي دقيق (فرق أشهر لا أيام): الأشهر أطوال متفاوتة
    (28-31 يوماً)، والقسمة على 30 كانت لتُخطئ حالات حقيقية تحرسها اختبارات
    موجودة (فجوات شهرية بأعداد أيام مختلفة). البقية فروق منتظمة، فالقسمة
    على طول الحبيبة الاسمي بالأيام (config.GRANULARITY_DAYS) كافية.
    """
    if granularity == "monthly":
        return (dates[-1].year - dates[0].year) * 12 + (dates[-1].month - dates[0].month) + 1
    if granularity == "yearly":
        return dates[-1].year - dates[0].year + 1
    period_days = config.GRANULARITY_DAYS[granularity]
    return round((dates[-1] - dates[0]).days / period_days) + 1


def _finalize(
    pivoted: pd.DataFrame, warnings: list[Warning_], categories: dict[str, str] | None = None
) -> Dataset:
    """من إطار مُحوَّر (فهرس = منتجات، أعمدة = تسميات أشهر) إلى Dataset جاهز.

    مشتركة بين مسارَي التخمين التلقائي والربط اليدوي: كلاهما ينتج نفس
    الشكل بعد _from_long/_from_wide، والترتيب والتحذيرات لا تفرّق بين
    مصدر الأعمدة — فلا يجوز أن تتكرر.
    """
    # التواريخ كاملةً أولاً: الحبيبة تُقاس منها، وقصّ اليوم يمحوها.
    labels = [str(column) for column in pivoted.columns]
    parsed_full: list[tuple[str, date | None]] = [
        (label, parse_full_date(label)) for label in labels
    ]
    full_dates = [parsed for _, parsed in parsed_full if parsed]

    # الحبيبة الفعلية — تُكتشَف لا تُفرَض. كل الحبيبات الخمس مقبولة (بند 1
    # في docs/ROADMAP.md). العلامة الصريحة في التسمية (W#/Q#/سنة مجرّدة)
    # أصدق من الفجوة فتُقدَّم، ثم الفجوات، ثم الشهري عند الغموض التام
    # (تاريخان لا يكفيان لقياس فارق) — وهو ما كانت البوابة القديمة تفعله.
    granularity = (
        detect_granularity_from_labels(labels)
        or detect_granularity(full_dates)
        or DEFAULT_GRANULARITY
    )

    # قصّ اليوم إلى بداية الشهر مناسب للشهري فقط — تصديرة قد تضع أي يوم
    # داخل عمود شهر واحد، واليوم عندها ضجيج لا معلومة. لغير الشهري اليوم
    # *هو* ما يميّز عموداً عن آخر (أسبوعان في يناير لهما نفس الشهر ويومان
    # مختلفان تماماً) — قصّه كان يُصيّر كليهما "2024-01-01" فيُفسد الترتيب
    # وحساب الفجوات معاً. راجع تعليق _expected_period_count.
    if granularity == "monthly":
        parsed_periods: list[tuple[str, date | None]] = [
            (label, date(parsed.year, parsed.month, 1) if parsed else None)
            for label, parsed in parsed_full
        ]
    else:
        parsed_periods = parsed_full
    understood = [(label, parsed) for label, parsed in parsed_periods if parsed]

    if not understood:
        raise DataValidationError(
            "لم يُفهَم أي عمود كتاريخ. الأشكال المقبولة: "
            "'يناير 2023'، 'Jan 2023'، '2023-01'.",
            context={
                "code": "no_months",
                "columns": [label for label, _ in parsed_periods][:6],
            },
        )

    unreadable = [label for label, parsed in parsed_periods if not parsed]
    if unreadable:
        warnings.append(Warning_("dropped_columns", {
            "count": len(unreadable), "names": "، ".join(unreadable[:4]),
        }))

    understood.sort(key=lambda pair: pair[1])
    ordered_labels = [label for label, _ in understood]
    pivoted = pivoted[ordered_labels]

    if len(ordered_labels) < MIN_MONTHS:
        raise DataValidationError(
            f"{len(ordered_labels)} فترة فقط ({granularity}) — الحد الأدنى {MIN_MONTHS}.",
            context={
                "code": "too_few_months",
                "months": len(ordered_labels),
                "minimum": MIN_MONTHS,
                "granularity": granularity,
            },
        )

    # فجوات زمنية: تسلسل ناقص يُفسد الموسمية بصمت
    dates = [parsed for _, parsed in understood]
    expected = _expected_period_count(dates, granularity)
    if expected != len(dates):
        warnings.append(Warning_("timeline_gaps", {
            "found": len(dates), "expected": expected,
            "start": str(dates[0]), "end": str(dates[-1]),
            "granularity": granularity,
        }))

    numeric = pivoted.apply(to_numeric)
    # ما تعذّر قراءته يصير صفراً — وهو استبدال يغيّر التوصية، فيجب أن
    # يُسمّى المنتج المتأثّر لا أن يُعدّ فقط. تحذير "قيمتان غير رقميتين"
    # على كتالوج فيه 185 منتجاً لا يقول لأحد أين ينظر.
    unreadable = numeric.isna() & pivoted.notna()
    non_numeric = int(unreadable.sum().sum())
    if non_numeric > 0:
        affected = [str(name) for name in pivoted.index[unreadable.any(axis=1)]]
        warnings.append(Warning_("non_numeric", {
            "count": non_numeric,
            "products": "، ".join(affected[:4]),
            "product_count": len(affected),
        }))
    numeric = numeric.fillna(0.0)

    negatives = int((numeric < 0).sum().sum())
    if negatives:
        warnings.append(Warning_("negatives", {"count": negatives}))
        numeric = numeric.clip(lower=0)

    products: dict[str, list[float]] = {}
    for name, row in numeric.iterrows():
        label = str(name).strip()
        if label and label.lower() != "nan":
            products[label] = [float(v) for v in row.tolist()]

    if not products:
        raise DataValidationError(
            "لا منتجات صالحة في الملف", context={"code": "no_products"}
        )

    dead = sum(1 for values in products.values() if sum(values) == 0)
    if dead:
        warnings.append(Warning_("dead_products", {"count": dead}))

    # حصر الفئات بمنتجات وصلت فعلاً — دفاعي لا حاسم: category_of قد يحمل
    # اسماً سقط هنا (تسمية فارغة، صفّ "nan") فلا يبقى يتيماً في Dataset.
    kept_categories = {
        name: category for name, category in (categories or {}).items() if name in products
    }

    return Dataset(
        months=ordered_labels,
        products=products,
        start_date=dates[0],
        granularity=granularity,
        warnings=warnings,
        categories=kept_categories,
    )


def parse_upload(content: bytes, filename: str) -> Dataset:
    """قراءة ملف مرفوع وتحويله إلى Dataset — الأعمدة تُخمَّن بالاسم.

    Raises:
        DataValidationError: ملف غير مقروء، أو بلا أشهر مفهومة، أو بلا
            منتجات — أي حالة لا يُنتج معها المحرك شيئاً ذا معنى.
            code="no_months" تحديداً يعني: التخمين فشل في تحديد الأعمدة
            (شكل طويل بأسماء غير معروفة) أو تسميات الأشهر نفسها غير
            مفهومة (شكل عريض برؤوس أعمدة غريبة). كلاهما قابل للإنقاذ عبر
            parse_upload_with_mapping إن كفى عدد الأعمدة.
    """
    frame = _read_file(content, filename)
    if frame.empty:
        raise DataValidationError(
            "الملف فارغ", context={"code": "empty_file", "filename": filename}
        )

    layout = _detect_layout(frame)
    if layout == "long":
        columns = [str(c) for c in frame.columns]
        pivoted, warnings, categories = _from_long(
            frame,
            _find_column(columns, PRODUCT_HINTS),
            _find_column(columns, MONTH_HINTS),
            _find_column(columns, QUANTITY_HINTS),
            _find_column(columns, CATEGORY_HINTS),
        )
    else:
        pivoted, warnings = _from_wide(frame)
        categories = {}  # لا عمود فئة ممكن هيكلياً في الشكل العريض

    return _finalize(pivoted, warnings, categories)


def parse_upload_with_mapping(
    content: bytes,
    filename: str,
    *,
    product_column: str,
    month_column: str,
    quantity_column: str,
) -> Dataset:
    """كـ parse_upload، لكن بأعمدة اختارها المستخدم يدوياً بدل التخمين.

    الطريق حين تفشل PRODUCT_HINTS/MONTH_HINTS/QUANTITY_HINTS في التقاط
    عمود حقيقي — المستخدم يعرف ملفه أفضل من أي قائمة تلميحات مهما اتّسعت،
    وتوسيع القائمة بالتخمين محفوظ الرفض (راجع تعليق PRODUCT_HINTS أعلاه).
    يفترض الشكل الطويل صراحة — لا معنى لربط ثلاثة أدوار على ملف عريض.

    Raises:
        DataValidationError: عمود مختار غير موجود في الملف، أو تكرار
            نفس العمود لأكثر من دور، أو ما يرفضه _finalize (حبيبة غير
            مدعومة، أشهر قليلة، منتجات فارغة).
    """
    frame = _read_file(content, filename)
    if frame.empty:
        raise DataValidationError(
            "الملف فارغ", context={"code": "empty_file", "filename": filename}
        )

    columns = [str(c) for c in frame.columns]
    chosen = {
        "product": product_column,
        "month": month_column,
        "quantity": quantity_column,
    }
    for role, column in chosen.items():
        if column not in columns:
            raise DataValidationError(
                f"العمود المختار لـ{role} غير موجود في الملف: {column}",
                context={"code": "unknown_mapped_column", "role": role, "column": column},
            )
    if len(set(chosen.values())) < 3:
        raise DataValidationError(
            "اختر ثلاثة أعمدة مختلفة — نفس العمود لا يصلح لدورين",
            context={"code": "duplicate_mapped_columns"},
        )

    pivoted, warnings, categories = _from_long(
        frame, product_column, month_column, quantity_column
    )
    return _finalize(pivoted, warnings, categories)


def to_csv_template() -> bytes:
    """نموذج فارغ يوضّح الشكل المتوقَّع — أسرع من شرحه بالكلام."""
    frame = pd.DataFrame(
        {
            "المنتج": ["Hydraulic Pump 50mm", "Safety Valve 2in"],
            "يناير 2024": [120, 45],
            "فبراير 2024": [95, 0],
            "مارس 2024": [130, 60],
        }
    )
    return frame.to_csv(index=False).encode("utf-8-sig")


def _stock_from_columns(
    frame: pd.DataFrame, product_column: str, stock_column: str,
    price_column: str | None = None,
) -> StockSnapshot:
    """من عمودين معلومَي الاسم إلى {منتج: مخزون} — تخميناً أو يدوياً، كما
    _from_long لملف المبيعات. الجمع عند التكرار لا الأخذ الأول: صفّان
    لنفس المنتج غالباً مستودعان لا خطأ إدخال، ومخزونهما الحقيقي مجموعهما.

    price_column اختياري بالكامل — لا يشارك في اكتشاف الشكل ولا يُرفَض
    غيابه، كـ CATEGORY_HINTS في ملف المبيعات. حين يوجد: أول قيمة غير
    فارغة لكل منتج تُؤخَذ سعره — السعر صفة شبه ثابتة للمنتج لا قيمة
    تتكرر لتُجمَع كالمخزون.
    """
    warnings: list[Warning_] = []
    duplicates = int(frame.duplicated(subset=[product_column]).sum())
    if duplicates:
        warnings.append(Warning_("stock_duplicate_rows", {"count": duplicates}))

    grouped = frame.groupby(product_column)[stock_column].sum()
    numeric = to_numeric(grouped)
    non_numeric = int(numeric.isna().sum())
    if non_numeric:
        # نفس عقد الوسائط الذي يستعمله مسار المبيعات: الرمز واحد فيجب أن
        # يكون النصّ قابلاً للتنسيق من كليهما.
        affected = [str(name) for name in numeric.index[numeric.isna()]]
        warnings.append(Warning_("non_numeric", {
            "count": non_numeric,
            "products": "، ".join(affected[:4]),
            "product_count": len(affected),
        }))
    numeric = numeric.fillna(0.0)

    negatives = int((numeric < 0).sum())
    if negatives:
        warnings.append(Warning_("negatives", {"count": negatives}))
        numeric = numeric.clip(lower=0)

    levels: dict[str, float] = {}
    for name, value in numeric.items():
        label = str(name).strip()
        if label and label.lower() != "nan":
            levels[label] = float(value)

    if not levels:
        raise DataValidationError(
            "لا منتجات صالحة في ملف المخزون", context={"code": "no_products"}
        )

    prices: dict[str, float] = {}
    if price_column is not None:
        first_price = to_numeric(
            frame.groupby(product_column)[price_column].first()
        )
        for name, value in first_price.items():
            label = str(name).strip()
            if label and label in levels and pd.notna(value) and value >= 0:
                prices[label] = float(value)

    return StockSnapshot(levels=levels, warnings=warnings, prices=prices)


def parse_stock_upload(content: bytes, filename: str) -> StockSnapshot:
    """قراءة ملف مخزون (عمودان: منتج + مخزون حالي، وعمود سعر اختياري
    ثالث) — الأعمدة تُخمَّن بالاسم.

    Raises:
        DataValidationError: ملف غير مقروء، أو فارغ، أو تعذّر تخمين عمود
            المنتج أو المخزون (code="no_stock_columns" — قابل للإنقاذ عبر
            parse_stock_upload_with_mapping)، أو بلا منتجات صالحة.
    """
    frame = _read_file(content, filename)
    if frame.empty:
        raise DataValidationError(
            "الملف فارغ", context={"code": "empty_file", "filename": filename}
        )

    columns = [str(c) for c in frame.columns]
    product_column = _find_column(columns, PRODUCT_HINTS)
    stock_column = _find_column(columns, STOCK_HINTS)
    if product_column is None or stock_column is None:
        raise DataValidationError(
            "لم يُفهَم عمود المنتج أو عمود المخزون",
            context={"code": "no_stock_columns", "columns": columns[:6]},
        )

    price_column = _find_column(columns, PRICE_HINTS)
    return _stock_from_columns(frame, product_column, stock_column, price_column)


def parse_stock_upload_with_mapping(
    content: bytes, filename: str, *, product_column: str, stock_column: str
) -> StockSnapshot:
    """كـ parse_stock_upload، لكن بعمودين اختارهما المستخدم يدوياً بدل التخمين."""
    frame = _read_file(content, filename)
    if frame.empty:
        raise DataValidationError(
            "الملف فارغ", context={"code": "empty_file", "filename": filename}
        )

    columns = [str(c) for c in frame.columns]
    chosen = {"product": product_column, "stock": stock_column}
    for role, column in chosen.items():
        if column not in columns:
            raise DataValidationError(
                f"العمود المختار لـ{role} غير موجود في الملف: {column}",
                context={"code": "unknown_mapped_column", "role": role, "column": column},
            )
    if product_column == stock_column:
        raise DataValidationError(
            "اختر عمودين مختلفين — نفس العمود لا يصلح لدورين",
            context={"code": "duplicate_mapped_columns"},
        )

    return _stock_from_columns(frame, product_column, stock_column)


def stock_csv_template() -> bytes:
    """نموذج فارغ لملف المخزون — عمودان إلزاميان، وعمود سعر اختياري ثالث
    (يُستخدم في خطة الشراء لحساب التكلفة التقديرية إن وُجد)."""
    frame = pd.DataFrame(
        {
            "المنتج": ["Hydraulic Pump 50mm", "Safety Valve 2in"],
            "المخزون الحالي": [50, 0],
            "سعر الوحدة (اختياري)": [120.0, 45.0],
        }
    )
    return frame.to_csv(index=False).encode("utf-8-sig")

