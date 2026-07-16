# services/forecast_engine/__init__.py
"""
محرك التنبؤ (Phase 3).

واجهة موحّدة تُدرّب Naive/MovingAverage/ETS/SARIMA/Prophet/XGBoost/
RandomForest، تقيّم كلاً منها على بيانات لم يرَها، وتختار الأفضل.

    from services.forecast_engine import forecast_product

    result = forecast_product("منتج", series, steps=6)
    result.best             # ForecastResult (domain entity)
    result.best_model_name  # "ETS"
    result.ranking()        # كل النماذج المقيَّمة، الأفضل أولاً

النماذج تُضاف في registry.py — المحرك لا يعرف أياً منها بالاسم.
"""
from .base import Forecaster, ForecastOutput
from .engine import EngineResult, ModelEvaluation, forecast_product
from .evaluation import ModelMetrics, backtest, compute_metrics
from .intermittent import DemandClass, DemandProfile, classify_demand
from .registry import applicable_models, default_models

__all__ = [
    "Forecaster",
    "ForecastOutput",
    "ForecastResult",
    "EngineResult",
    "ModelEvaluation",
    "ModelMetrics",
    "DemandClass",
    "DemandProfile",
    "classify_demand",
    "forecast_product",
    "backtest",
    "compute_metrics",
    "default_models",
    "applicable_models",
]

from domain.entities import ForecastResult  # noqa: E402  (إعادة تصدير للراحة)
