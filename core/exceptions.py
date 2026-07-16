# core/exceptions.py
"""
تسلسل هرمي موحّد للاستثناءات في النظام.

الهدف: استبدال أنماط `except Exception: pass` المتناثرة في الكود الحالي
(مثل models/forecasting.py, repositories/json_repository.py) باستثناءات
واضحة يمكن التقاطها ومعالجتها بشكل مركزي في app.py / ui layer.

لا يغيّر هذا الملف أي سلوك موجود؛ الوحدات الحالية تستمر بالعمل كما هي.
الاستخدام يكون تدريجياً: كل service جديد أو مُعاد هيكلته يرفع هذه
الاستثناءات بدلاً من ابتلاع الأخطاء بصمت.
"""


class AppError(Exception):
    """الأب المشترك لكل استثناءات النظام. يُستخدم للـ catch العام في app.py"""

    def __init__(self, message: str, *, cause: Exception | None = None, context: dict | None = None):
        super().__init__(message)
        self.message = message
        self.cause = cause
        self.context = context or {}

    def __str__(self) -> str:
        base = self.message
        if self.context:
            base += f" | context={self.context}"
        return base


# ---------------------------------------------------------------------------
# أخطاء البيانات (Repository / Data Access)
# ---------------------------------------------------------------------------
class DataAccessError(AppError):
    """فشل في قراءة/كتابة البيانات (JSON أو SQLite)."""


class DataValidationError(AppError):
    """البيانات موجودة لكنها غير صالحة (قيم سالبة، أعمدة ناقصة، تكرار...)."""


class MigrationError(AppError):
    """فشل ترحيل البيانات بين JSON و SQLite."""


# ---------------------------------------------------------------------------
# أخطاء التنبؤ (Forecasting)
# ---------------------------------------------------------------------------
class ForecastError(AppError):
    """فشل عام في التنبؤ."""


class InsufficientDataError(ForecastError):
    """البيانات غير كافية لتدريب نموذج معيّن (عدد نقاط أقل من الحد الأدنى)."""


class ModelTrainingError(ForecastError):
    """فشل تدريب نموذج تنبؤ محدد (ETS/SARIMA/Prophet/XGBoost/RF)."""


class ModelSelectionError(ForecastError):
    """فشل في اختيار أفضل نموذج (كل النماذج فشلت أو المقاييس غير صالحة)."""


# ---------------------------------------------------------------------------
# أخطاء القرار والمخزون (سيُستخدم في المراحل 4-5)
# ---------------------------------------------------------------------------
class DecisionEngineError(AppError):
    """فشل في توليد توصية إنتاجية."""


class InventoryError(AppError):
    """خطأ في بيانات أو حسابات المخزون (نقاط إعادة الطلب، المخزون الآمن...)."""


# ---------------------------------------------------------------------------
# أخطاء الإعدادات
# ---------------------------------------------------------------------------
class ConfigurationError(AppError):
    """إعداد ناقص أو غير صالح في core.app_config."""
