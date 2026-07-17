# tests/test_phase0_foundation.py
"""
أساس Phase 0 الباقي: الاستثناءات، الـlogging، وكيانات الـdomain.

كان هنا أربعة اختبارات لـ core.app_config حتى حُذفت الوحدة: طبقة إعدادات
كُتبت في Phase 0 لتحلّ محلّ config.py، بخطة دمج من ثلاث خطوات في رأسها،
لم تُنفَّذ الخطوة الثانية منها قط. لم يستوردها شيء إلا هذه الاختبارات.

وأحدها كان يقول:

    assert not os.path.exists(s.cache_path) or True

وهو تعبير قيمته True مهما كان الطرف الأول — اختبار لا يؤكّد شيئاً، اسمه
يَعِد بحراسة الآثار الجانبية ولا يحرسها. دقّة الوحدة المحذوفة نفسها.
"""
import logging

from core.exceptions import AppError, ForecastError, InsufficientDataError
from core.logging_config import get_logger, setup_logging
from domain.entities import (
    ForecastResult,
    ProductionRecommendation,
    RiskLevel,
    RiskScore,
)


# ---------------------------------------------------------------------------
# core.exceptions
# ---------------------------------------------------------------------------
def test_app_error_carries_context():
    err = AppError("فشل عام", context={"product": "X"})
    assert "فشل عام" in str(err)
    assert "product" in str(err)


def test_exception_hierarchy():
    assert issubclass(InsufficientDataError, ForecastError)
    assert issubclass(ForecastError, AppError)


# ---------------------------------------------------------------------------
# core.logging_config
# ---------------------------------------------------------------------------
def test_setup_logging_is_idempotent(tmp_path):
    setup_logging(log_dir=str(tmp_path))
    handlers_before = len(logging.getLogger().handlers)
    setup_logging(log_dir=str(tmp_path))  # لا يجب أن يضيف handlers مكررة
    handlers_after = len(logging.getLogger().handlers)
    assert handlers_before == handlers_after


def test_get_logger_returns_named_logger():
    logger = get_logger("test.module")
    assert logger.name == "test.module"


# ---------------------------------------------------------------------------
# domain.entities
# ---------------------------------------------------------------------------
def test_risk_level_from_score():
    assert RiskLevel.from_score(10) == RiskLevel.LOW
    assert RiskLevel.from_score(50) == RiskLevel.MEDIUM
    assert RiskLevel.from_score(90) == RiskLevel.HIGH


def test_forecast_result_next_period_value():
    fr = ForecastResult(
        product_name="X",
        model_name="ETS",
        forecast_values=[100.0, 110.0],
        lower_bound=[90.0, 95.0],
        upper_bound=[110.0, 125.0],
    )
    assert fr.next_period_value == 100.0


def test_production_recommendation_message_format():
    rec = ProductionRecommendation(
        product_name="Hydraulic Pump 50mm",
        recommended_quantity=12500,
        reason="ارتفاع الطلب المتوقع",
        expected_demand_change_pct=18.0,
    )
    msg = rec.as_message()
    assert "12,500" in msg
    assert "Hydraulic Pump 50mm" in msg
    assert "18.0%" in msg


def test_risk_score_level_property():
    rs = RiskScore(
        product_name="X",
        score=75,
        demand_volatility=0.5,
        stock_depletion_risk=0.8,
        forecast_accuracy_penalty=0.2,
        seasonality_factor=0.1,
        growth_rate=0.05,
    )
    assert rs.level == RiskLevel.HIGH
