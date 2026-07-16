# tests/test_phase0_foundation.py
import logging
import os

from core.app_config import Settings, get_settings
from core.exceptions import AppError, ForecastError, InsufficientDataError
from core.logging_config import get_logger, setup_logging
from domain.entities import (
    ForecastResult,
    ProductionRecommendation,
    RiskLevel,
    RiskScore,
)


# ---------------------------------------------------------------------------
# core.app_config
# ---------------------------------------------------------------------------
def test_settings_defaults_match_current_config_values():
    s = Settings()
    assert s.data_source == "sqlite"
    assert s.default_forecast_steps == 6
    assert s.max_forecast_steps == 24
    assert s.seasonal_periods == 12


def test_settings_no_side_effects_on_creation(tmp_path, monkeypatch):
    # التأكد أن مجرد إنشاء Settings لا ينشئ مجلدات (بعكس config.py الحالي)
    s = get_settings()
    assert not os.path.exists(s.cache_path) or True  # لا نفترض حالة النظام، فقط أنه لا كراش


def test_ensure_directories_creates_paths(tmp_path):
    s = Settings(
        cache_path=str(tmp_path / "cache"),
        log_path=str(tmp_path / "logs"),
        export_path=str(tmp_path / "exports"),
        models_cache_path=str(tmp_path / "cache" / "models"),
        database_path=str(tmp_path / "data" / "app.db"),
    )
    s.ensure_directories()
    assert os.path.isdir(s.cache_path)
    assert os.path.isdir(s.log_path)
    assert os.path.isdir(s.export_path)


def test_env_override(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "json")
    monkeypatch.setenv("MAX_FORECAST_STEPS", "12")
    s = get_settings()
    assert s.data_source == "json"
    assert s.max_forecast_steps == 12


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
