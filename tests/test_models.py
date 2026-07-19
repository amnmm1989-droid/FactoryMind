# tests/test_models.py
"""
models/statistics.py — الاتجاه والشواذّ.

اختبارا forecast_ets/forecast_sarima حُذفا مع models/forecasting.py نفسه:
كان مسار تنبؤ ثانياً لا يستعمله إلا صفحة المحلّل القديمة، ونموذجه ترتيبه
8/9 على هذا الكتالوج. مسار التنبؤ الوحيد الآن services/forecast_engine —
اختباراته في tests/test_forecast_engine.py.

trend_analysis يبقى: يستعمله services/risk_service/factors.py لعامل
الاتجاه في حساب الخطورة.
"""
from models.statistics import detect_outliers_iqr, trend_analysis

# بيانات اختبار ثابتة (مأخوذة من عينة من data.json)
SAMPLE_SERIES = [5, 82, 89, 74, 99, 77, 95, 93, 152, 178, 117, 147, 171, 162, 179, 172, 150, 165, 236, 229, 258, 333, 260, 234, 187, 332, 179, 348, 184, 283, 269, 228, 215, 182, 101, 237, 198, 114, 123, 292, 239, 199, 249, 127]


def test_trend_analysis():
    trend = trend_analysis(SAMPLE_SERIES)
    assert 'slope' in trend
    assert 'r_squared' in trend
    # رموز لا نصوص منذ إضافة الإنجليزية: النص المعروض كان يُبنى هنا،
    # فيظهر حرفياً في واجهة إنجليزية بلا أي مكان لترجمته. العرض في ui/i18n.
    assert trend['direction'] in ["up", "down", "flat"]


def test_detect_outliers_iqr():
    outliers, lower, upper = detect_outliers_iqr(SAMPLE_SERIES)
    assert isinstance(outliers, list)
    assert len(outliers) >= 0
