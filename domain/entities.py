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
    """درجة الخطورة لمنتج معيّن (0-100) مع تفصيل العوامل المُساهمة."""
    product_name: str
    score: float  # 0-100
    demand_volatility: float
    stock_depletion_risk: float
    forecast_accuracy_penalty: float
    seasonality_factor: float
    growth_rate: float

    @property
    def level(self) -> RiskLevel:
        return RiskLevel.from_score(self.score)


@dataclass(frozen=True)
class ProductionRecommendation:
    """توصية إنتاجية قابلة للعرض مباشرة في الـ Dashboard."""
    product_name: str
    recommended_quantity: float
    reason: str  # مثال: "بسبب ارتفاع الطلب المتوقع بنسبة 18%"
    expected_demand_change_pct: float
    risk: RiskScore | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_message(self) -> str:
        direction = "ارتفاع" if self.expected_demand_change_pct >= 0 else "انخفاض"
        return (
            f"يوصى بإنتاج {self.recommended_quantity:,.0f} وحدة من المنتج "
            f"{self.product_name} في الشهر القادم بسبب {direction} الطلب "
            f"المتوقع بنسبة {abs(self.expected_demand_change_pct):.1f}%"
        )


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
