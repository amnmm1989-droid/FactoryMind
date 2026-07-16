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
PAGE_TITLE = "نظام تحليل وتنبؤ متقدم"
PAGE_ICON = "🔮"
LAYOUT = "wide"
INITIAL_SIDEBAR_STATE = "expanded"

DEFAULT_FORECAST_STEPS = 6
MAX_FORECAST_STEPS = 24
SEASONAL_PERIODS = 12
CONFIDENCE_LEVEL = 1.96

SHOW_TREND_DEFAULT = True
SHOW_SEASONAL_DEFAULT = True
SHOW_CORRELATION_DEFAULT = True
SHOW_DISTRIBUTION_DEFAULT = True
SHOW_OUTLIERS_DEFAULT = True