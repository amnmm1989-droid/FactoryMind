# services/ingest.py
"""
قراءة بيانات المستخدم من CSV/Excel.

هذا الملف يحوّل المشروع من "أداة لبياناتنا" إلى "أداة لبيانات أي مصنع".
قبله لم يكن هناك أي مسار لإدخال بيانات: `data/data.json` مثبَّت في
config.py، ولا `file_uploader` في الكود كله.

يقبل الشكلين اللذين يُصدّرهما العالم الحقيقي:

    عريض (wide) — الأشيع، مخرج Excel/ERP المعتاد:
        المنتج    | يناير 2023 | فبراير 2023 | ...
        بنّ برازيلي |    120     |     95      | ...

    طويل (long) — مخرج قواعد البيانات:
        المنتج     | الشهر       | الكمية
        بنّ برازيلي | يناير 2023  | 120

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

# تلميحات أسماء الأعمدة في الشكل الطويل
PRODUCT_HINTS = ("product", "item", "sku", "المنتج", "الصنف", "المادة")
MONTH_HINTS = ("month", "date", "period", "الشهر", "التاريخ", "الفترة")
QUANTITY_HINTS = ("quantity", "qty", "amount", "value", "sales", "الكمية", "العدد", "المبيعات")

MIN_MONTHS = 3  # أقل من ذلك لا يُنتج تنبؤاً ذا معنى بأي نموذج


@dataclass
class Dataset:
    """بيانات جاهزة للمحرّكات + ما يجب أن يعرفه المستخدم عنها."""

    months: list[str]                      # التسميات كما يراها المستخدم
    products: dict[str, list[float]]
    start_date: date | None                # مشتقّ من الملف، لا مثبَّت
    warnings: list[str] = field(default_factory=list)

    @property
    def product_count(self) -> int:
        return len(self.products)

    @property
    def month_count(self) -> int:
        return len(self.months)


def parse_month_label(label: str) -> date | None:
    """تحويل تسمية شهر إلى تاريخ. None إن تعذّر — لا تخمين.

    يفهم: "يناير 2023"، "Jan 2023"، "2023-01"، "01/2023"، "Jan-23"...
    ولا يفهم: "الشهر الأول"، "P1"، "أسبوع 3" — وتلك تُرجع None ليُحذَّر
    المستخدم بدل أن تُخمَّن.
    """
    text = str(label).strip()
    if not text:
        return None

    # عربي: اسم الشهر + سنة
    for name, number in ARABIC_MONTHS.items():
        if name in text:
            year_match = re.search(r"(1[89]\d{2}|20\d{2})", text)
            if year_match:
                return date(int(year_match.group(1)), number, 1)
            return None

    # الباقي: pandas أقدر على أشكال التاريخ الإنجليزية والرقمية
    try:
        parsed = pd.to_datetime(text, errors="raise", dayfirst=False)
        return date(parsed.year, parsed.month, 1)
    except (ValueError, TypeError, pd.errors.ParserError):
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
            context={"filename": filename},
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


def _from_long(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    columns = [str(c) for c in frame.columns]
    product_column = _find_column(columns, PRODUCT_HINTS)
    month_column = _find_column(columns, MONTH_HINTS)
    quantity_column = _find_column(columns, QUANTITY_HINTS)

    warnings: list[str] = []
    duplicates = frame.duplicated(subset=[product_column, month_column]).sum()
    if duplicates:
        # الجمع لا الأخذ الأول: صفّان لنفس المنتج/الشهر يعنيان طلبين
        warnings.append(f"{duplicates} صفاً مكرّراً (منتج+شهر) — جُمعت كمياتها.")

    pivoted = frame.pivot_table(
        index=product_column, columns=month_column,
        values=quantity_column, aggfunc="sum", fill_value=0,
    )
    return pivoted, warnings


def _from_wide(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    if frame.shape[1] < 2:
        raise DataValidationError(
            "الملف يحتاج عمود أسماء وعمود شهر واحداً على الأقل",
            context={"columns": frame.shape[1]},
        )
    return frame.set_index(frame.columns[0]), []


def parse_upload(content: bytes, filename: str) -> Dataset:
    """قراءة ملف مرفوع وتحويله إلى Dataset.

    Raises:
        DataValidationError: ملف غير مقروء، أو بلا أشهر مفهومة، أو بلا
            منتجات — أي حالة لا يُنتج معها المحرك شيئاً ذا معنى.
    """
    frame = _read_file(content, filename)
    if frame.empty:
        raise DataValidationError("الملف فارغ", context={"filename": filename})

    layout = _detect_layout(frame)
    pivoted, warnings = _from_long(frame) if layout == "long" else _from_wide(frame)

    # ترتيب الأشهر زمنياً — لا بترتيب ظهورها في الملف. عمود "يناير" قبل
    # "ديسمبر" في ملف المستخدم يعني سنة تالية، لا شهراً سابقاً.
    parsed_months: list[tuple[str, date | None]] = [
        (str(column), parse_month_label(column)) for column in pivoted.columns
    ]
    understood = [(label, parsed) for label, parsed in parsed_months if parsed]

    if not understood:
        raise DataValidationError(
            "لم يُفهَم أي عمود كشهر. الأشكال المقبولة: "
            "'يناير 2023'، 'Jan 2023'، '2023-01'.",
            context={"columns": [label for label, _ in parsed_months][:6]},
        )

    unreadable = [label for label, parsed in parsed_months if not parsed]
    if unreadable:
        warnings.append(
            f"{len(unreadable)} عموداً لم يُفهَم كشهر فأُهمل: "
            f"{'، '.join(unreadable[:4])}"
        )

    understood.sort(key=lambda pair: pair[1])
    ordered_labels = [label for label, _ in understood]
    pivoted = pivoted[ordered_labels]

    if len(ordered_labels) < MIN_MONTHS:
        raise DataValidationError(
            f"{len(ordered_labels)} شهراً فقط — الحد الأدنى {MIN_MONTHS}.",
            context={"months": len(ordered_labels)},
        )

    # فجوات زمنية: تسلسل ناقص يُفسد الموسمية بصمت
    dates = [parsed for _, parsed in understood]
    expected = (dates[-1].year - dates[0].year) * 12 + (dates[-1].month - dates[0].month) + 1
    if expected != len(dates):
        warnings.append(
            f"فجوات في التسلسل الزمني: {len(dates)} شهراً موجوداً من {expected} "
            f"بين {dates[0]} و{dates[-1]}. الأشهر الناقصة ليست أصفاراً — هي غياب "
            "بيانات، والموسمية المحسوبة عليها غير دقيقة."
        )

    numeric = pivoted.apply(pd.to_numeric, errors="coerce")
    non_numeric = int(numeric.isna().sum().sum() - pivoted.isna().sum().sum())
    if non_numeric > 0:
        warnings.append(f"{non_numeric} خلية غير رقمية عوملت كصفر.")
    numeric = numeric.fillna(0.0)

    negatives = int((numeric < 0).sum().sum())
    if negatives:
        warnings.append(
            f"{negatives} قيمة سالبة (مرتجعات؟) — رُفعت إلى صفر. "
            "المحرّكات تتعامل مع الطلب لا صافي الحركة."
        )
        numeric = numeric.clip(lower=0)

    products: dict[str, list[float]] = {}
    for name, row in numeric.iterrows():
        label = str(name).strip()
        if label and label.lower() != "nan":
            products[label] = [float(v) for v in row.tolist()]

    if not products:
        raise DataValidationError("لا منتجات صالحة في الملف")

    dead = sum(1 for values in products.values() if sum(values) == 0)
    if dead:
        warnings.append(
            f"{dead} منتجاً بلا أي مبيعات — لا ينطبق عليها نموذج، وستُرفض صراحةً."
        )

    return Dataset(
        months=ordered_labels,
        products=products,
        start_date=dates[0],
        warnings=warnings,
    )


def to_csv_template() -> bytes:
    """نموذج فارغ يوضّح الشكل المتوقَّع — أسرع من شرحه بالكلام."""
    frame = pd.DataFrame(
        {
            "المنتج": ["بنّ برازيلي 1kg", "بنّ إثيوبي 250g"],
            "يناير 2024": [120, 45],
            "فبراير 2024": [95, 0],
            "مارس 2024": [130, 60],
        }
    )
    return frame.to_csv(index=False).encode("utf-8-sig")
