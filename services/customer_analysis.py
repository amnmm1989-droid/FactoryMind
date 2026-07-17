# services/customer_analysis.py
"""
البُعد الثالث: العميل (Roadmap بند 5) — تحليل فقط، لا إنشاء طلبات.

مدير المبيعات يستقبل الطلبات، لا يُصدرها. هذا الملف يجيب ثلاثة أسئلة لا
تجيبها أي صفحة أخرى: من يُركِّز عليه الخطر؟ من ينزف؟ ومن ينمو؟ كلّها
حسابات بلا Streamlit — قابلة للاختبار بمعزل عنه، كبقية services/*.
"""
from __future__ import annotations

from dataclasses import dataclass

from services.ingest import CustomerSalesDataset

# نمو أقل من هذا يُعدّ "نزيفاً" لا تذبذباً طبيعياً. عتبة لا حدّاً علمياً:
# اختيار عملي يفصل انحداراً حقيقياً عن تقلّب شهري عادي.
BLEEDING_THRESHOLD_PCT = -20.0


@dataclass(frozen=True)
class ConcentrationRow:
    """حصة عميل واحد من إجمالي الكتالوج، وحصته التراكمية بترتيب النزول."""

    customer: str
    quantity: float
    share_pct: float
    cumulative_share_pct: float


def concentration(dataset: CustomerSalesDataset) -> list[ConcentrationRow]:
    """ترتيب العملاء بحصتهم من الإجمالي — تركّز أم توزّع الاعتماد عليهم؟

    إجمالي صفري (كل الكميات صفر) يعني حصصاً غير معرَّفة رياضياً — قائمة
    فارغة بدل نسب مخترعة تبدو دقيقة وهي عشوائية (0/0).
    """
    totals = {
        customer: sum(sum(values) for values in products.values())
        for customer, products in dataset.rows.items()
    }
    grand_total = sum(totals.values())
    if grand_total <= 0:
        return []

    ranked = sorted(totals.items(), key=lambda pair: pair[1], reverse=True)
    rows: list[ConcentrationRow] = []
    cumulative = 0.0
    for customer, quantity in ranked:
        share = quantity / grand_total * 100
        cumulative += share
        rows.append(ConcentrationRow(customer, quantity, share, cumulative))
    return rows


@dataclass(frozen=True)
class GrowthRow:
    """نمو عميل واحد: متوسط النصف الثاني من نافذة الملف مقابل الأول.

    growth_pct=None يعني: النصف الأول صفر بالكامل، فنسبة النمو من صفر غير
    معرَّفة رياضياً (لا نهائية) — لا تُعرَض كصفر أو رقم مخترَع.
    """

    customer: str
    first_half_avg: float
    second_half_avg: float
    growth_pct: float | None


def growth_by_customer(dataset: CustomerSalesDataset) -> list[GrowthRow]:
    """نمو كل عميل داخل نافذة الملف — النصف الثاني مقابل الأول.

    ليس أفضل نموذج نمو ممكن (انحدار خطي مثلاً)، بل الأبسط الذي يُفسَّر
    بجملة واحدة: "أكثر بـ س% في النصف الثاني" — نفس تفضيل هذا المشروع
    للتفسير الواضح على التعقيد غير المُثبَت الفائدة (راجع Bottom-Up في
    services/reconciliation.py لنفس المبدأ).
    """
    totals = dataset.customer_totals()
    midpoint = len(dataset.months) // 2

    rows: list[GrowthRow] = []
    for customer, series in totals.items():
        first_half = series[:midpoint]
        second_half = series[midpoint:]
        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)
        growth = (
            (second_avg - first_avg) / first_avg * 100 if first_avg > 0 else None
        )
        rows.append(GrowthRow(customer, first_avg, second_avg, growth))
    return rows


def bleeding_customers(
    dataset: CustomerSalesDataset, *, threshold_pct: float = BLEEDING_THRESHOLD_PCT
) -> list[GrowthRow]:
    """عملاء نموّهم سلبي بوضوح (تحت threshold_pct) — الأشد انحداراً أولاً.

    None (نمو غير معرَّف) ليس نزيفاً: عميل بلا مبيعات في النصف الأول لم
    يكن عميلاً بعد، لا عميلاً ينسحب.
    """
    rows = growth_by_customer(dataset)
    bleeding = [r for r in rows if r.growth_pct is not None and r.growth_pct <= threshold_pct]
    return sorted(bleeding, key=lambda r: r.growth_pct)
