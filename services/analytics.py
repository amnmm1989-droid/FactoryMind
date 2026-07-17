# services/analytics.py
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

def prepare_forecast_months(last_month_idx, months, steps):
    """توليد تسميات الأشهر المتوقَّعة، بصيغة ISO (YYYY-MM).

    ⚠️ إصلاح خطأ: كانت الدالة تفعل `months[(last_month_idx + i) % len(months)]`
    — أي تلتفّ إلى *بداية* السلسلة. تنبؤ ما بعد يوليو 2026 كان يُسمّى
    "ديسمبر 2022"، فتُرسَم نقاط التنبؤ على مواضع تاريخية وتصطدم بها على
    محور فئوي. الاختبار الوحيد كان يفحص الطول، فمرّ الخطأ.

    الصيغة ISO لا مترجَمة: هذه طبقة خدمات. ui.i18n.format_month يفهمها
    ويعرضها باللغة المختارة ("August 2026" / "أغسطس 2026").

    تراجُع آمن: تسمية أخيرة غير مفهومة (ملف مستخدم بتسميات مخصّصة)
    تُنتج "+1، +2..." — صريحة في أنها إزاحة، لا تاريخ مخترَع.
    """
    from services.ingest import parse_month_label

    last_label = months[last_month_idx] if 0 <= last_month_idx < len(months) else None
    last_date = parse_month_label(last_label) if last_label else None

    if last_date is None:
        return [f"+{i}" for i in range(1, steps + 1)]

    labels = []
    for i in range(1, steps + 1):
        total = last_date.month - 1 + i
        labels.append(f"{last_date.year + total // 12}-{total % 12 + 1:02d}")
    return labels

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