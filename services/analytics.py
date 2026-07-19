# services/analytics.py
"""
إحصاءات وصفية لسلسلة منتج واحد.

## ما حُذف من هنا ولماذا

- `prepare_seasonal_data`: كان يقسّم المدى إلى أربعة مقاطع متساوية ويسمّيها
  "أرباعاً". لم تكن موسمية أصلاً (لا علاقة لها بموضع الفترة في الدورة)،
  فحُذف مع القسم الذي كان يعرضه.
- `prepare_forecast_months`: توليد تسميات فترات التنبؤ لصفحة المحلّل
  القديمة — زال بزوال التنبؤ منها. تسميات تنبؤ المحرك الحالي تُبنى في
  services/forecast_engine.

راجع ui/dashboard.py وservices/product_analysis_service.py للقرار كاملاً.
"""
import numpy as np


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
