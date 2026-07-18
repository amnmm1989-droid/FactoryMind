# services/analytics.py
from datetime import date, timedelta

import numpy as np
import pandas as pd
from config import SEASONAL_PERIODS

def compute_basic_stats(series):
    """حساب الإحصائيات الأساسية"""
    total = np.sum(series)
    avg = np.mean(series)
    max_val = np.max(series)
    min_val = min([v for v in series if v > 0], default=0)
    std_val = np.std(series)
    median_val = np.median(series)
    cv = std_val / avg if avg != 0 else 0
    non_zero_count = np.sum(np.array(series) > 0)
    last_val = series[-1] if len(series) > 0 else 0
    return {
        'total': total,
        'avg': avg,
        'max': max_val,
        'min': min_val,
        'std': std_val,
        'median': median_val,
        'cv': cv,
        'non_zero_count': non_zero_count,
        'last_val': last_val
    }

def _future_label(last_date: date, i: int, granularity: str) -> str:
    """التسمية بعد i فترة من last_date، بالشكل الذي يطابق حبيبة الملف.

    كلٌّ يعود إلى شكله الأصلي فيتركه ui.i18n.format_month كما هو (غير
    الشهري ليس "شهراً مجرّداً")، والشهري يبقى ISO فيُترجَم كالسابق تماماً.
    """
    if granularity == "yearly":
        return str(last_date.year + i)
    if granularity == "quarterly":
        total = (last_date.month - 1) + i * 3
        return f"Q{total % 12 // 3 + 1} {last_date.year + total // 12}"
    if granularity == "weekly":
        iso = (last_date + timedelta(weeks=i)).isocalendar()
        return f"W{iso.week} {iso.year}"
    if granularity == "daily":
        return (last_date + timedelta(days=i)).isoformat()
    # الشهري (والافتراضي): إضافة أشهر، بصيغة ISO (YYYY-MM)
    total = last_date.month - 1 + i
    return f"{last_date.year + total // 12}-{total % 12 + 1:02d}"


def prepare_forecast_months(last_month_idx, months, steps, granularity="monthly"):
    """توليد تسميات الفترات المتوقَّعة، كلٌّ بحبيبة الملف الفعلية.

    ⚠️ إصلاح خطأ: كانت الدالة تفعل `months[(last_month_idx + i) % len(months)]`
    — أي تلتفّ إلى *بداية* السلسلة. تنبؤ ما بعد يوليو 2026 كان يُسمّى
    "ديسمبر 2022"، فتُرسَم نقاط التنبؤ على مواضع تاريخية وتصطدم بها على
    محور فئوي. الاختبار الوحيد كان يفحص الطول، فمرّ الخطأ.

    الحبيبة تُمرَّر لا تُفترَض: ملف أسبوعي يخطو أسبوعاً لا شهراً، فلا
    يُسمّى تنبؤ الأسبوع القادم بشهر كامل. الشهري (الافتراضي) يبقى ISO
    (YYYY-MM) بلا تغيير — عقد الاختبارات القائمة. ui.i18n.format_month
    يعرض ISO الشهري باللغة المختارة، ويترك W#/Q#/سنة/يوم كما هي.

    تراجُع آمن: تسمية أخيرة غير مفهومة (ملف مستخدم بتسميات مخصّصة)
    تُنتج "+1، +2..." — صريحة في أنها إزاحة، لا تاريخ مخترَع.
    """
    from services.ingest import parse_full_date, parse_month_label

    last_label = months[last_month_idx] if 0 <= last_month_idx < len(months) else None
    # الشهري يقصّ لأول الشهر (سلوكه الأصلي)؛ غيره يحتاج التاريخ الكامل
    # ليخطو بالأسبوع/اليوم الصحيح لا بأول شهرٍ ضاع يومه.
    if not last_label:
        last_date = None
    elif granularity == "monthly":
        last_date = parse_month_label(last_label)
    else:
        last_date = parse_full_date(last_label)

    if last_date is None:
        return [f"+{i}" for i in range(1, steps + 1)]

    return [_future_label(last_date, i, granularity) for i in range(1, steps + 1)]

# مفاتيح ثابتة لا تُترجَم: 'الربع 1' كانت قيمةً *وترتيباً* (groupby +
# Categorical). ترجمتها هنا كانت ستكسر الفرز وتثبّت العربية في طبقة
# خدمات لا علاقة لها بالعرض. ui/charts.py يترجم للعرض.
QUARTER_KEY = "_quarter"
QUANTITY_KEY = "_qty"
QUARTER_ORDER = ("q1", "q2", "q3", "q4")


def prepare_seasonal_data(selected_months, series):
    """تحضير البيانات للتحليل الموسمي (أرباع السنة)"""
    df = pd.DataFrame({QUANTITY_KEY: series})
    n = len(df)
    quarter_size = n // 4
    remainder = n % 4
    quarters = []
    for i in range(4):
        size = quarter_size + (1 if i < remainder else 0)
        quarters.extend([QUARTER_ORDER[i]] * size)
    if len(quarters) < n:
        quarters.extend([QUARTER_ORDER[3]] * (n - len(quarters)))
    df[QUARTER_KEY] = quarters[:n]
    seasonal_avg = df.groupby(QUARTER_KEY)[QUANTITY_KEY].mean().reset_index()
    seasonal_avg[QUARTER_KEY] = pd.Categorical(
        seasonal_avg[QUARTER_KEY], categories=list(QUARTER_ORDER), ordered=True
    )
    return seasonal_avg.sort_values(QUARTER_KEY)