# domain/entities.py
"""
كائنات Domain نقية (بدون أي اعتماد على Streamlit/SQLite/Pandas).

هذا الملف هو "العقد" الذي ستُبنى عليه المراحل القادمة:
  - Phase 3 (Forecast Engine)  -> يُرجع ForecastResult
  - Phase 4 (Decision Engine)  -> يُرجع ProductionRecommendation
  - Phase 5 (Inventory)        -> يستخدم InventoryStatus / RiskLevel

لا يوجد بعد أي منطق أعمال هنا (سيُضاف في المراحل التالية)، فقط
التعريفات الهيكلية التي تسمح لبقية النظام (dashboard, tests) بالتطور
تدريجياً دون الانتظار حتى تكتمل كل الميزات دفعة واحدة.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"        # 0-30
    MEDIUM = "medium"   # 30-70
    HIGH = "high"        # 70-100

    @staticmethod
    def from_score(score: float) -> "RiskLevel":
        if score < 30:
            return RiskLevel.LOW
        if score < 70:
            return RiskLevel.MEDIUM
        return RiskLevel.HIGH


class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


@dataclass(frozen=True)
class ForecastResult:
    """نتيجة تنبؤ موحّدة بغض النظر عن النموذج المستخدم (ETS/SARIMA/Prophet/XGBoost/RF)."""
    product_name: str
    model_name: str
    forecast_values: list[float]
    lower_bound: list[float]
    upper_bound: list[float]
    mae: float | None = None
    rmse: float | None = None
    mape: float | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def next_period_value(self) -> float | None:
        return self.forecast_values[0] if self.forecast_values else None


@dataclass(frozen=True)
class RiskScore:
    """درجة الخطورة لمنتج معيّن (0-100) مع تفصيل العوامل المُساهمة.

    كل عامل مساهمة خطورة على مقياس 0-100 (لا قيمة خام): 0 = لا خطورة،
    100 = أقصاها. التوحيد ضروري ليكون الجمع الموزون ذا معنى.

    None يعني "غير معروف" لا "صفر" — والفرق حاسم:
      - stock_depletion_risk = 0   -> المخزون وفير، لا خطر نفاد
      - stock_depletion_risk = None -> لا نعرف المخزون أصلاً
    خلطهما يجعل منتجاً مجهول المخزون يبدو آمناً. العوامل المجهولة
    تُستبعد من الحساب وتُعاد موازنة الباقي (services/risk_service).
    """
    product_name: str
    score: float  # 0-100
    demand_volatility: float | None
    stock_depletion_risk: float | None
    forecast_accuracy_penalty: float | None
    seasonality_factor: float | None
    growth_rate: float | None

    @property
    def level(self) -> RiskLevel:
        return RiskLevel.from_score(self.score)

    @property
    def known_factors(self) -> dict[str, float]:
        """العوامل المحسوبة فعلاً — ما دخل في score."""
        candidates = {
            "demand_volatility": self.demand_volatility,
            "stock_depletion_risk": self.stock_depletion_risk,
            "forecast_accuracy_penalty": self.forecast_accuracy_penalty,
            "seasonality_factor": self.seasonality_factor,
            "growth_rate": self.growth_rate,
        }
        return {name: value for name, value in candidates.items() if value is not None}

    @property
    def missing_factors(self) -> list[str]:
        """العوامل التي تعذّر حسابها — يجب أن تُعرض مع الدرجة لا أن تُخفى.

        درجة محسوبة من عاملين ليست كدرجة محسوبة من خمسة، ومن يقرأ الرقم
        يستحق أن يعرف على أي أساس بُني.
        """
        all_names = {
            "demand_volatility",
            "stock_depletion_risk",
            "forecast_accuracy_penalty",
            "seasonality_factor",
            "growth_rate",
        }
        return sorted(all_names - set(self.known_factors))

    @property
    def confidence(self) -> float:
        """نسبة العوامل المعروفة (0-1) — مقياس صريح لصلابة الدرجة."""
        return len(self.known_factors) / 5.0


@dataclass(frozen=True)
class ProductionRecommendation:
    """توصية إنتاجية قابلة للعرض مباشرة في الـ Dashboard."""
    product_name: str
    recommended_quantity: float
    reason: str  # مثال: "بسبب ارتفاع الطلب المتوقع بنسبة 18%"
    expected_demand_change_pct: float
    risk: RiskScore | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # تحت هذه النسبة يُعتبر الطلب مستقراً لا متغيّراً
    STABLE_THRESHOLD_PCT = 0.05

    def as_message(self) -> str:
        """رسالة التوصية الجاهزة للعرض.

        حالة الاستقرار ليست تفصيلاً تجميلياً: النموذج الفائز على معظم
        منتجات هذا المشروع متوسط متحرك، وهو يتنبأ بحكم تعريفه بأن الشهر
        القادم كالأشهر الماضية — أي تغيّر ~0%. الصياغة القديمة كانت تقرأ
        الصفر كـ"ارتفاع" وتُخرج "بسبب ارتفاع الطلب المتوقع بنسبة 0.0%".
        """
        quantity = f"{self.recommended_quantity:,.0f}"
        if abs(self.expected_demand_change_pct) < self.STABLE_THRESHOLD_PCT:
            return (
                f"يوصى بإنتاج {quantity} وحدة من المنتج {self.product_name} "
                f"في الشهر القادم — الطلب المتوقع مستقر"
            )

        direction = "ارتفاع" if self.expected_demand_change_pct > 0 else "انخفاض"
        return (
            f"يوصى بإنتاج {quantity} وحدة من المنتج "
            f"{self.product_name} في الشهر القادم بسبب {direction} الطلب "
            f"المتوقع بنسبة {abs(self.expected_demand_change_pct):.1f}%"
        )


@dataclass(frozen=True)
class ProductStats:
    """إحصائيات أساسية لمنتج — تقابل تماماً مخرجات services.analytics.compute_basic_stats
    لكن ككائن مكتوب بدل قاموس خام، لتفادي أخطاء المفاتيح الإملائية."""
    product_name: str
    total: float
    avg: float
    max: float
    min: float
    std: float
    median: float
    cv: float
    non_zero_count: int
    last_val: float


@dataclass(frozen=True)
class TrendAnalysis:
    """تقابل مخرجات models.statistics.trend_analysis."""
    product_name: str
    slope: float
    intercept: float
    r_squared: float
    p_value: float
    direction: str

    @property
    def direction_enum(self) -> TrendDirection:
        if self.slope > 0:
            return TrendDirection.UP
        if self.slope < 0:
            return TrendDirection.DOWN
        return TrendDirection.STABLE


@dataclass(frozen=True)
class OutlierReport:
    """تقابل مخرجات models.statistics.detect_outliers_iqr."""
    product_name: str
    outlier_indices: list[int]
    lower_bound: float
    upper_bound: float

    @property
    def has_outliers(self) -> bool:
        return len(self.outlier_indices) > 0

    @property
    def count(self) -> int:
        return len(self.outlier_indices)


@dataclass(frozen=True)
class InventoryStatus:
    """حالة مخزون منتج (تُستخدم بالكامل في Phase 5)."""
    product_name: str
    current_stock: float
    minimum_stock: float
    safety_stock: float
    reorder_point: float
    lead_time_days: int

    @property
    def needs_reorder(self) -> bool:
        return self.current_stock <= self.reorder_point

    @property
    def stockout_risk(self) -> bool:
        return self.current_stock <= self.safety_stock
