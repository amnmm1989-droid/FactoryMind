# tests/test_calibration.py
"""
معايرة FACTOR_WEIGHTS من نتائج فعلية (Roadmap: "Still open" تحت بندي
Phase 4 وبند 4 — الآن بعد أن صار actual_quantity قابلاً للتعبئة).

المحور: عيّنة صغيرة أو عامل مفقود لا يُنتجان رقماً واثقاً كاذباً — نفس
مبدأ None٪ في risk_service نفسه مطبَّقاً على الارتباط الإحصائي هذه المرة.
"""
from __future__ import annotations

import pytest

from services.risk_service.calibration import (
    FACTOR_NAMES,
    MIN_SAMPLE_PER_FACTOR,
    calibrate,
    planning_error,
)


# ---------------------------------------------------------------------------
# خطأ التخطيط لخطة واحدة
# ---------------------------------------------------------------------------
def test_exact_plan_has_zero_error():
    assert planning_error(planned=100.0, actual=100.0) == 0.0


def test_overproduction_and_underproduction_are_symmetric():
    over = planning_error(planned=150.0, actual=100.0)
    under = planning_error(planned=50.0, actual=100.0)

    assert over == pytest.approx(0.5)
    assert under == pytest.approx(0.5)


def test_zero_actual_gives_undefined_error_not_zero_or_infinity():
    """قسمة على صفر غير معرَّفة رياضياً — لا صفر (يوهم بخطة مثالية) ولا
    رقم أقصى مخترَع."""
    assert planning_error(planned=50.0, actual=0.0) is None
    assert planning_error(planned=0.0, actual=0.0) is None


# ---------------------------------------------------------------------------
# المعايرة الكاملة
# ---------------------------------------------------------------------------
def _row(risk_factor: float | None, error: float, **overrides) -> dict:
    planned = 100.0
    actual = planned / (1 + error) if error >= 0 else planned * (1 - error)
    row = {
        "planned_quantity": planned, "actual_quantity": actual,
        "demand_volatility": None, "stock_depletion_risk": None,
        "forecast_accuracy_penalty": None, "seasonality_factor": None,
        "growth_rate": None,
    }
    if risk_factor is not None:
        row["demand_volatility"] = risk_factor
    row.update(overrides)
    return row


def test_a_factor_below_the_sample_floor_is_not_correlated():
    """أقل من MIN_SAMPLE_PER_FACTOR زوجاً — لا ارتباط يُحسَب، مهما بدا واضحاً."""
    rows = [_row(risk_factor=float(i), error=float(i) / 10) for i in range(3)]

    report = calibrate(rows)

    demand_volatility = next(c for c in report.correlations if c.factor == "demand_volatility")
    assert demand_volatility.correlation is None
    assert demand_volatility.sample_size == 3
    assert "demand_volatility" in report.unvalidated_factors


def test_a_factor_missing_from_every_row_is_unvalidated_with_zero_sample():
    rows = [_row(risk_factor=None, error=0.1) for _ in range(20)]

    report = calibrate(rows)

    stock = next(c for c in report.correlations if c.factor == "stock_depletion_risk")
    assert stock.correlation is None
    assert stock.sample_size == 0


def test_a_perfectly_predictive_factor_gets_correlation_near_one():
    """العامل يرتفع تماماً مع خطأ التخطيط — ارتباط قريب من 1."""
    rows = [
        _row(risk_factor=float(i), error=float(i) / 100)
        for i in range(MIN_SAMPLE_PER_FACTOR + 5)
    ]

    report = calibrate(rows)

    demand_volatility = next(c for c in report.correlations if c.factor == "demand_volatility")
    assert demand_volatility.correlation == pytest.approx(1.0, abs=0.01)
    assert demand_volatility.sample_size == MIN_SAMPLE_PER_FACTOR + 5


def test_a_constant_factor_has_undefined_correlation_not_zero():
    """كل الصفوف بنفس قيمة العامل بالضبط — لا تباين، فالارتباط غير معرَّف
    (لا صفر يوهم بأن العامل بلا علاقة، بل لم يُختبَر أصلاً)."""
    rows = [
        _row(risk_factor=50.0, error=float(i) / 100)
        for i in range(MIN_SAMPLE_PER_FACTOR + 5)
    ]

    report = calibrate(rows)

    demand_volatility = next(c for c in report.correlations if c.factor == "demand_volatility")
    assert demand_volatility.correlation is None


def test_suggested_weights_favour_the_more_predictive_factor():
    rows = []
    for i in range(MIN_SAMPLE_PER_FACTOR + 5):
        row = _row(risk_factor=float(i), error=float(i) / 100)
        row["growth_rate"] = 50.0 + (i % 3)  # ضجيج ضعيف الارتباط
        rows.append(row)

    report = calibrate(rows)

    assert report.suggested_weights is not None
    assert report.suggested_weights["demand_volatility"] > report.suggested_weights.get(
        "growth_rate", 0.0
    )
    assert sum(report.suggested_weights.values()) == pytest.approx(1.0)


def test_a_negatively_correlated_factor_is_excluded_not_given_negative_weight():
    """عامل يرتفع حين *يسهل* التخطيط (ارتباط سالب) يُستبعد من الوزن —
    لا يُعكَس إلى وزن سالب، ولا يُصفَّر معناه (correlation يبقى ظاهراً)."""
    rows = [
        _row(risk_factor=100.0 - i, error=float(i) / 100)
        for i in range(MIN_SAMPLE_PER_FACTOR + 5)
    ]

    report = calibrate(rows)

    demand_volatility = next(c for c in report.correlations if c.factor == "demand_volatility")
    assert demand_volatility.correlation < 0
    assert "demand_volatility" not in (report.suggested_weights or {})


def test_no_suggested_weights_when_nothing_is_validated():
    rows = [_row(risk_factor=None, error=0.1) for _ in range(20)]

    report = calibrate(rows)

    assert report.suggested_weights is None


def test_calibrate_on_no_outcomes_at_all_reports_zero_not_a_crash():
    report = calibrate([])

    assert report.total_outcomes == 0
    assert report.suggested_weights is None
    assert all(c.correlation is None for c in report.correlations)


def test_every_factor_name_is_reported_even_when_unvalidated():
    report = calibrate([])

    assert {c.factor for c in report.correlations} == set(FACTOR_NAMES)
