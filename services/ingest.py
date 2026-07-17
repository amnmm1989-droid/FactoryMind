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

MIN_MONTHS = 3  # أقل من ذلك لا يُنتج تنبؤاً ذا معنى بأي نموذج

# الحبيبة الزمنية: الفارق النمطي بالأيام -> الاسم.
# المشروع يدعم الشهري وحده اليوم؛ الباقي يُرفَض صراحةً لا يُقبَل ويُساء
# تفسيره. راجع docs/ROADMAP.md — "الحبيبة الزمنية المرنة".
GRANULARITY_BUCKETS = {
    1: "daily",
    7: "weekly",
    30: "monthly",
    91: "quarterly",
    365: "yearly",
}
SUPPORTED_GRANULARITY = "monthly"


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
    warnings: list[Warning_] = field(default_factory=list)

    @property
    def product_count(self) -> int:
        return len(self.products)

    @property
    def month_count(self) -> int:
        return len(self.months)


def parse_full_date(label: str) -> date | None:
    """تحويل تسمية إلى تاريخ **باليوم** — لا يُقصّ.

    الفارق عن parse_month_label جوهري وليس تفصيلاً: قصّ اليوم يجعل
    2025-01-06 و2025-01-13 و2025-01-20 كلها 2025-01-01، فتضيع الحبيبة
    الزمنية *قبل* أن تُقاس. الكشف يحتاج التواريخ كاملة.

    تسمية شهرية بلا يوم ("يناير 2023") تُرجع اليوم الأول — وهو الصحيح:
    البيانات الشهرية لا يوم لها.
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
        return SUPPORTED_GRANULARITY

    smallest_gap = min(
        (unique[i + 1] - unique[i]).days for i in range(len(unique) - 1)
    )
    return GRANULARITY_BUCKETS[
        min(GRANULARITY_BUCKETS, key=lambda b: abs(smallest_gap - b))
    ]


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
    frame: pd.DataFrame, product_column: str, month_column: str, quantity_column: str
) -> tuple[pd.DataFrame, list[Warning_]]:
    """محور (منتج × شهر) من ثلاثة أعمدة معلومة الاسم — تخميناً أو يدوياً.

    الأعمدة تصل جاهزة لا تُكتشَف هنا: parse_upload يمرّرها من _find_column
    (التخمين)، وparse_upload_with_mapping يمرّرها من اختيار المستخدم
    (شاشة الربط اليدوي). المحور نفسه لا يفرّق بين الحالتين — وهذا مقصود:
    خطأ في التخمين وخطأ في اختيار المستخدم يُعاملان بمعيار واحد.
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
    return pivoted, warnings


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

    role: "product" | "month" | "quantity". يستخدم نفس تلميحات التخمين
    التلقائي (PRODUCT_HINTS إلخ) — تخمين أفضل من لا شيء، لكنه يبقى تخميناً
    يُعرض على المستخدم لا يُفرَض عليه؛ الشاشة تسمح بتغييره بنقرة.
    """
    hints = {
        "product": PRODUCT_HINTS,
        "month": MONTH_HINTS,
        "quantity": QUANTITY_HINTS,
    }[role]
    return _find_column(columns, hints)


def _finalize(pivoted: pd.DataFrame, warnings: list[Warning_]) -> Dataset:
    """من إطار مُحوَّر (فهرس = منتجات، أعمدة = تسميات أشهر) إلى Dataset جاهز.

    مشتركة بين مسارَي التخمين التلقائي والربط اليدوي: كلاهما ينتج نفس
    الشكل بعد _from_long/_from_wide، وبوابة الحبيبة والترتيب والتحذيرات
    لا تفرّق بين مصدر الأعمدة — فلا يجوز أن تتكرر.
    """
    # التواريخ كاملةً أولاً: الحبيبة تُقاس منها، وقصّ اليوم يمحوها.
    parsed_full: list[tuple[str, date | None]] = [
        (str(column), parse_full_date(column)) for column in pivoted.columns
    ]
    full_dates = [parsed for _, parsed in parsed_full if parsed]

    # بوابة الحبيبة — قبل أي بناء.
    #
    # بدونها كان ملف أسبوعي *يُقبَل* ويُعامَل كأشهر: 30 أسبوعاً تُقرأ 30
    # شهراً، وSEASONAL_PERIODS=12 يبحث عن دورة كل 12 *أسبوعاً* ويسمّيها
    # سنوية. لا خطأ يظهر — فقط تحليل واثق وخاطئ، وهو أسوأ ما يمكن أن
    # تفعله أداة دعواها أنها تعرف متى لا تعرف.
    granularity = detect_granularity(full_dates)
    if granularity is not None and granularity != SUPPORTED_GRANULARITY:
        raise DataValidationError(
            f"بيانات {granularity} — المدعوم حالياً: {SUPPORTED_GRANULARITY}",
            context={
                "code": "unsupported_granularity",
                "granularity": granularity,
                "supported": SUPPORTED_GRANULARITY,
            },
        )

    # ترتيب الأشهر زمنياً — لا بترتيب ظهورها في الملف. عمود "يناير" قبل
    # "ديسمبر" في ملف المستخدم يعني سنة تالية، لا شهراً سابقاً.
    parsed_months: list[tuple[str, date | None]] = [
        (label, date(parsed.year, parsed.month, 1) if parsed else None)
        for label, parsed in parsed_full
    ]
    understood = [(label, parsed) for label, parsed in parsed_months if parsed]

    if not understood:
        raise DataValidationError(
            "لم يُفهَم أي عمود كشهر. الأشكال المقبولة: "
            "'يناير 2023'، 'Jan 2023'، '2023-01'.",
            context={
                "code": "no_months",
                "columns": [label for label, _ in parsed_months][:6],
            },
        )

    unreadable = [label for label, parsed in parsed_months if not parsed]
    if unreadable:
        warnings.append(Warning_("dropped_columns", {
            "count": len(unreadable), "names": "، ".join(unreadable[:4]),
        }))

    understood.sort(key=lambda pair: pair[1])
    ordered_labels = [label for label, _ in understood]
    pivoted = pivoted[ordered_labels]

    if len(ordered_labels) < MIN_MONTHS:
        raise DataValidationError(
            f"{len(ordered_labels)} شهراً فقط — الحد الأدنى {MIN_MONTHS}.",
            context={
                "code": "too_few_months",
                "months": len(ordered_labels),
                "minimum": MIN_MONTHS,
            },
        )

    # فجوات زمنية: تسلسل ناقص يُفسد الموسمية بصمت
    dates = [parsed for _, parsed in understood]
    expected = (dates[-1].year - dates[0].year) * 12 + (dates[-1].month - dates[0].month) + 1
    if expected != len(dates):
        warnings.append(Warning_("timeline_gaps", {
            "found": len(dates), "expected": expected,
            "start": str(dates[0]), "end": str(dates[-1]),
        }))

    numeric = pivoted.apply(pd.to_numeric, errors="coerce")
    non_numeric = int(numeric.isna().sum().sum() - pivoted.isna().sum().sum())
    if non_numeric > 0:
        warnings.append(Warning_("non_numeric", {"count": non_numeric}))
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

    return Dataset(
        months=ordered_labels,
        products=products,
        start_date=dates[0],
        warnings=warnings,
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
        pivoted, warnings = _from_long(
            frame,
            _find_column(columns, PRODUCT_HINTS),
            _find_column(columns, MONTH_HINTS),
            _find_column(columns, QUANTITY_HINTS),
        )
    else:
        pivoted, warnings = _from_wide(frame)

    return _finalize(pivoted, warnings)


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

    pivoted, warnings = _from_long(frame, product_column, month_column, quantity_column)
    return _finalize(pivoted, warnings)


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
