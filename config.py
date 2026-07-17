# config.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ========== مسارات الملفات ==========
DATA_FILE = os.path.join(BASE_DIR, 'data', 'data.json')
CACHE_PATH = os.path.join(BASE_DIR, 'cache')
LOG_PATH = os.path.join(BASE_DIR, 'logs')
EXPORT_PATH = os.path.join(BASE_DIR, 'exports')
DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'app.db')

# ========== مصدر البيانات (اختر 'json' أو 'sqlite') ==========
DATA_SOURCE = 'sqlite'   # غيّر إلى 'json' للعودة إلى JSON مؤقتاً

# إنشاء المجلدات إذا لم تكن موجودة
for path in [CACHE_PATH, LOG_PATH, EXPORT_PATH, os.path.dirname(DATABASE_PATH)]:
    os.makedirs(path, exist_ok=True)

# ========== باقي الإعدادات (بدون تغيير) ==========
# لا PAGE_TITLE هنا: العنوان نصٌّ يراه المستخدم، فمكانه قاموس الترجمة
# (ui/i18n.page_title). نصٌّ مثبَّت بلغة واحدة في ملف إعدادات كان يجعل تبويب
# المتصفّح عربياً على صفحة إنجليزية.
PAGE_ICON = "🔮"
LAYOUT = "wide"
INITIAL_SIDEBAR_STATE = "expanded"

DEFAULT_FORECAST_STEPS = 6
MAX_FORECAST_STEPS = 24
SEASONAL_PERIODS = 12          # افتراضي شهري — راجع SEASONAL_PERIODS_BY_GRANULARITY
CONFIDENCE_LEVEL = 1.96

# طول الفترة الواحدة بالأيام — المصدر الوحيد لهذا التحويل (services/ingest.py
# يشتقّ GRANULARITY_BUCKETS منه بالعكس؛ services/risk_service يستخدمه لتحويل
# مهلة التوريد بالأيام إلى عدد فترات، أياً كانت حبيبة الملف).
GRANULARITY_DAYS = {
    "daily": 1, "weekly": 7, "monthly": 30, "quarterly": 91, "yearly": 365,
}

# طول الدورة الموسمية الواحدة، بوحدة الفترة نفسها — لـ ETS/SARIMA
# (seasonal_periods) ولتجميع seasonality_factor. اليومي استثناء: الدورة
# الأسبوعية (7) أدلّ على نمط يومي حقيقي (يوم الأسبوع) من دورة سنوية طولها
# 365 نقطة، تحتاج بيانات لا تتوفر عادة.
SEASONAL_PERIODS_BY_GRANULARITY = {
    "daily": 7, "weekly": 52, "monthly": 12, "quarterly": 4, "yearly": 1,
}

# فترات في السنة — يفترق عن SEASONAL_PERIODS_BY_GRANULARITY عند اليومي
# تحديداً: 365 يوماً في السنة، لا 7 (دورة الأسبوع). يتطابقان في البقية
# صدفة لا تصميماً (شهري: 12 دورة = 12 فترة/سنة أيضاً).
PERIODS_PER_YEAR_BY_GRANULARITY = {
    "daily": 365, "weekly": 52, "monthly": 12, "quarterly": 4, "yearly": 1,
}

# freq الذي يفهمه pandas/statsmodels/Prophet لكل حبيبة.
PANDAS_FREQ_BY_GRANULARITY = {
    "daily": "D", "weekly": "W", "monthly": "MS", "quarterly": "QS", "yearly": "YS",
}

SHOW_TREND_DEFAULT = True
SHOW_SEASONAL_DEFAULT = True
SHOW_CORRELATION_DEFAULT = True
SHOW_DISTRIBUTION_DEFAULT = True
SHOW_OUTLIERS_DEFAULT = True