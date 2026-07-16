# tests/test_forecast_engine.py
"""
اختبارات محرك التنبؤ (Phase 3).

التركيز على ما يمكن أن يكذب بصمت: MAPE مع الأصفار، نموذج يُدرَّب على
بيانات لا تكفيه، cache يُرجع نتيجة بيانات أخرى، واختيار "أفضل" بلا دليل.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from core.exceptions import InsufficientDataError, ModelSelectionError, ModelTrainingError
from services.forecast_engine import forecast_product
from services.forecast_engine.base import Forecaster, ForecastOutput
from services.forecast_engine.cache import cache_key, data_hash
from services.forecast_engine.evaluation import (
    ModelMetrics,
    backtest,
    choose_holdout,
    compute_metrics,
)
from services.forecast_engine.naive import MovingAverageForecaster, NaiveForecaster
from services.forecast_engine.registry import applicable_models, default_models
from services.forecast_engine.statistical import ETSForecaster, SARIMAForecaster
from services.forecast_engine.tree import RandomForestForecaster, XGBoostForecaster


# سلسلة موسمية واضحة، 48 نقطة — تكفي كل النماذج
SEASONAL = [
    100 + 30 * math.sin(i * math.pi / 6) + (i * 0.5) for i in range(48)
]
# سلسلة شحيحة — واقع 39% من منتجات هذا المشروع
SPARSE = [0.0] * 40 + [12.0, 0.0, 8.0, 5.0]


# ---------------------------------------------------------------------------
# العقد: can_handle
# ---------------------------------------------------------------------------
def test_naive_handles_a_single_point():
    assert NaiveForecaster().can_handle([5.0])


def test_seasonal_models_reject_sparse_series():
    """جوهر Phase 3: كل منتج له 44 نقطة، لكن معظمها أصفار.

    نموذج موسمي يقبل 4 قيم بين 40 صفراً سيُرجع رقماً — ورقم بلا أساس
    أخطر من رفض صريح، لأنه يبدو إجابة.
    """
    for model in (ETSForecaster(), SARIMAForecaster(), XGBoostForecaster()):
        assert not model.can_handle(SPARSE), f"{model.name} قبل سلسلة شحيحة"


def test_baselines_accept_sparse_series():
    """بدون هذا، المحرك يفشل على 72 من 185 منتجاً."""
    assert NaiveForecaster().can_handle(SPARSE)
    assert MovingAverageForecaster().can_handle(SPARSE)


def test_length_alone_does_not_qualify_a_series():
    """44 نقطة كلها أصفار عدا واحدة: الطول يكفي، المحتوى لا."""
    almost_empty = [0.0] * 43 + [7.0]

    assert len(almost_empty) >= ETSForecaster().min_points
    assert not ETSForecaster().can_handle(almost_empty)


# ---------------------------------------------------------------------------
# النماذج تُنتج مخرجات صالحة
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "model",
    [NaiveForecaster(), MovingAverageForecaster(), ETSForecaster(),
     SARIMAForecaster(), XGBoostForecaster(), RandomForestForecaster()],
    ids=lambda m: m.name,
)
def test_model_returns_requested_horizon(model):
    output = model.fit_predict(SEASONAL, steps=6)

    assert len(output.values) == 6
    assert len(output.lower) == 6
    assert len(output.upper) == 6


@pytest.mark.parametrize(
    "model",
    [NaiveForecaster(), MovingAverageForecaster(), ETSForecaster(),
     SARIMAForecaster(), XGBoostForecaster(), RandomForestForecaster()],
    ids=lambda m: m.name,
)
def test_model_output_is_finite_and_non_negative(model):
    """كمية منتَجة سالبة أو NaN ليست تنبؤاً متحفظاً — إنها بلا معنى."""
    output = model.fit_predict(SEASONAL, steps=6)

    assert all(math.isfinite(v) for v in output.values)
    assert all(v >= 0 for v in output.values)
    assert all(v >= 0 for v in output.lower)


@pytest.mark.parametrize(
    "model",
    [NaiveForecaster(), MovingAverageForecaster(), ETSForecaster(), SARIMAForecaster()],
    ids=lambda m: m.name,
)
def test_bounds_bracket_the_forecast(model):
    output = model.fit_predict(SEASONAL, steps=6)

    for low, value, high in zip(output.lower, output.values, output.upper):
        assert low <= value <= high


def test_naive_repeats_the_last_value():
    output = NaiveForecaster().fit_predict([10.0, 20.0, 33.0], steps=3)

    assert output.values == [33.0, 33.0, 33.0]


def test_moving_average_uses_its_window():
    output = MovingAverageForecaster(window=3).fit_predict([0.0, 0.0, 3.0, 6.0, 9.0], steps=2)

    assert output.values == [6.0, 6.0]  # متوسط (3, 6, 9)


def test_mismatched_output_lengths_are_rejected():
    with pytest.raises(ValueError, match="أطوال غير متطابقة"):
        ForecastOutput(values=[1.0, 2.0], lower=[0.0], upper=[3.0, 4.0])


def test_tree_models_are_deterministic():
    """random_state مثبّت — مقارنة نموذجين تتغير نتيجتها بين تشغيلين
    ليست مقارنة."""
    first = XGBoostForecaster().fit_predict(SEASONAL, steps=4)
    second = XGBoostForecaster().fit_predict(SEASONAL, steps=4)

    assert first.values == second.values


# ---------------------------------------------------------------------------
# MAPE والأصفار — الفخ الأساسي في هذه البيانات
# ---------------------------------------------------------------------------
def test_mape_is_none_when_every_actual_is_zero():
    """القسمة على صفر تعطي inf/nan. None صريح أصدق من رقم كاذب."""
    metrics = compute_metrics(actual=[0.0, 0.0, 0.0], predicted=[1.0, 2.0, 3.0], holdout_size=3)

    assert metrics.mape is None
    assert math.isfinite(metrics.mae)
    assert math.isfinite(metrics.rmse)


def test_mape_ignores_zeros_but_uses_the_rest():
    metrics = compute_metrics(actual=[0.0, 100.0], predicted=[5.0, 90.0], holdout_size=2)

    assert metrics.mape == pytest.approx(10.0)  # من القيمة غير الصفرية وحدها


def test_metrics_never_return_nan_on_zero_heavy_data():
    """الانحدار الذي يحرس ضد الفخ في models/forecasting.py:66."""
    metrics = compute_metrics(
        actual=[0.0, 0.0, 5.0, 0.0], predicted=[1.0, 1.0, 4.0, 1.0], holdout_size=4
    )

    assert math.isfinite(metrics.mae)
    assert math.isfinite(metrics.rmse)
    assert metrics.mape is None or math.isfinite(metrics.mape)


def test_perfect_prediction_scores_zero():
    metrics = compute_metrics(actual=[10.0, 20.0], predicted=[10.0, 20.0], holdout_size=2)

    assert metrics.mae == 0.0
    assert metrics.rmse == 0.0
    assert metrics.mape == pytest.approx(0.0)


def test_rmse_punishes_large_errors_more_than_mae():
    """سبب اختيار RMSE معياراً: خطأ فادح واحد أسوأ من عدة أخطاء صغيرة."""
    metrics = compute_metrics(actual=[0.0, 0.0, 0.0, 40.0], predicted=[0.0] * 4, holdout_size=4)

    assert metrics.rmse > metrics.mae


def test_compute_metrics_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="أطوال غير متطابقة"):
        compute_metrics(actual=[1.0, 2.0], predicted=[1.0], holdout_size=2)


# ---------------------------------------------------------------------------
# التقييم
# ---------------------------------------------------------------------------
def test_holdout_scales_with_series_length():
    assert choose_holdout(48) == 6      # مسقوف
    assert choose_holdout(20) == 4      # خُمس
    assert choose_holdout(3) == 1       # أرضية


def test_backtest_trains_only_on_hidden_data():
    metrics = backtest(NaiveForecaster(), SEASONAL)

    assert metrics is not None
    assert metrics.holdout_size == choose_holdout(len(SEASONAL))


def test_backtest_returns_none_when_training_data_runs_out():
    """'لم يُقيَّم' ليس 'قُيِّم وكان سيئاً' — الخلط بينهما يفسد الاختيار."""
    assert backtest(ETSForecaster(), SPARSE) is None


def test_metrics_comparison_prefers_lower_rmse():
    better = ModelMetrics(mae=5.0, rmse=6.0, mape=None, holdout_size=6)
    worse = ModelMetrics(mae=4.0, rmse=9.0, mape=None, holdout_size=6)

    assert better.is_better_than(worse)
    assert not worse.is_better_than(better)


def test_any_metrics_beat_no_metrics():
    metrics = ModelMetrics(mae=99.0, rmse=99.0, mape=None, holdout_size=6)

    assert metrics.is_better_than(None)


# ---------------------------------------------------------------------------
# البصمة والـ cache
# ---------------------------------------------------------------------------
def test_same_data_gives_same_hash():
    assert data_hash("منتج", [1.0, 2.0]) == data_hash("منتج", [1.0, 2.0])


def test_changed_data_gives_different_hash():
    assert data_hash("منتج", [1.0, 2.0]) != data_hash("منتج", [1.0, 2.1])


def test_different_products_never_share_a_hash():
    """تصادم هنا = عرض تنبؤ منتج مكان آخر."""
    assert data_hash("منتج أ", [1.0, 2.0]) != data_hash("منتج ب", [1.0, 2.0])


def test_horizon_is_part_of_the_cache_key():
    """التنبؤ بـ 6 أشهر ليس بادئة التنبؤ بـ 12 — النماذج التكرارية
    تُنتج مساراً مختلفاً لكل أفق."""
    six = cache_key("منتج", [1.0, 2.0], "ETS", 6)
    twelve = cache_key("منتج", [1.0, 2.0], "ETS", 12)

    assert six != twelve


def test_model_name_is_part_of_the_cache_key():
    ets = cache_key("منتج", [1.0, 2.0], "ETS", 6)
    naive = cache_key("منتج", [1.0, 2.0], "Naive", 6)

    assert ets != naive


# ---------------------------------------------------------------------------
# السجل
# ---------------------------------------------------------------------------
def test_registry_is_ordered_simplest_first():
    """الترتيب هو سياسة الاختيار حين تنعدم الأدلة."""
    names = [m.name for m in default_models()]

    assert names[0] == "Naive"
    assert names.index("Naive") < names.index("ETS") < names.index("XGBoost")


def test_registry_covers_every_model_the_roadmap_asks_for():
    names = {m.name for m in default_models()}

    assert {"ETS", "SARIMA", "Prophet", "XGBoost", "RandomForest"} <= names


def test_applicable_models_shrink_as_data_thins():
    rich = applicable_models(SEASONAL)
    poor = applicable_models(SPARSE)

    assert len(poor) < len(rich)
    assert {m.name for m in poor} == {"Naive", "MovingAverage"}


# ---------------------------------------------------------------------------
# المحرك
# ---------------------------------------------------------------------------
def test_engine_picks_the_lowest_rmse():
    result = forecast_product("منتج", SEASONAL, steps=6, use_cache=False)

    ranking = result.ranking()
    assert result.best_model_name == ranking[0].model_name
    assert all(
        ranking[i].metrics.rmse <= ranking[i + 1].metrics.rmse
        for i in range(len(ranking) - 1)
    )


def test_engine_records_every_model_it_tried():
    """جدول model_performance يحتاج الخاسرين أيضاً — سجل القرار لا نتيجته."""
    result = forecast_product("منتج", SEASONAL, steps=6, use_cache=False)

    assert len(result.evaluations) == len(applicable_models(SEASONAL))


def test_engine_falls_back_to_baselines_on_sparse_data():
    """السيناريو الأكثر شيوعاً في هذه البيانات: 39% من المنتجات."""
    result = forecast_product("منتج شحيح", SPARSE, steps=3, use_cache=False)

    assert result.best_model_name in {"Naive", "MovingAverage"}
    assert len(result.best.forecast_values) == 3


def test_engine_prefers_simplicity_without_evidence():
    """بلا تقييم ممكن، لا نشتري تعقيداً لا دليل على فائدته."""
    result = forecast_product("قصير", [4.0, 5.0, 6.0], steps=2, use_cache=False)

    assert result.best_model_name == "Naive"
    assert result.evaluated_count >= 0


def test_engine_rejects_an_empty_series():
    with pytest.raises(InsufficientDataError):
        forecast_product("فارغ", [], steps=6, use_cache=False)


def test_engine_rejects_an_all_zero_series():
    """منتج بلا مبيعات قط: لا نموذج ينطبق — والرفض الصريح هو الجواب."""
    with pytest.raises(InsufficientDataError):
        forecast_product("أصفار", [0.0] * 44, steps=6, use_cache=False)


def test_engine_rejects_a_non_positive_horizon():
    with pytest.raises(ValueError):
        forecast_product("منتج", SEASONAL, steps=0, use_cache=False)


def test_engine_result_carries_the_data_hash():
    """يربط النتيجة بالبيانات التي وُلّدت منها — عمود forecasts.data_hash."""
    result = forecast_product("منتج", SEASONAL, steps=6, use_cache=False)

    assert result.data_hash == data_hash("منتج", SEASONAL)


def test_engine_survives_a_model_that_explodes():
    """نموذج واحد فاشل لا يُسقط التنبؤ — يُسجَّل ويُستكمل بالبقية."""

    class BrokenForecaster(Forecaster):
        name = "Broken"
        min_points = 1
        min_non_zero = 1

        def fit_predict(self, series, steps):
            raise ModelTrainingError("انفجرت عمداً")

    result = forecast_product(
        "منتج", SEASONAL, steps=3,
        models=[BrokenForecaster(), NaiveForecaster()], use_cache=False,
    )

    assert result.best_model_name == "Naive"
    broken = next(e for e in result.evaluations if e.model_name == "Broken")
    assert broken.error is not None
    assert not broken.succeeded


def test_engine_raises_when_every_model_fails():
    class BrokenForecaster(Forecaster):
        name = "Broken"
        min_points = 1
        min_non_zero = 1

        def fit_predict(self, series, steps):
            raise ModelTrainingError("انفجرت عمداً")

    with pytest.raises(ModelSelectionError, match="فشلت كل النماذج"):
        forecast_product("منتج", SEASONAL, steps=3, models=[BrokenForecaster()], use_cache=False)


def test_engine_returns_a_domain_entity():
    """العقد مع Phase 4: ForecastResult لا قاموس خام."""
    result = forecast_product("منتج", SEASONAL, steps=6, use_cache=False)

    assert result.best.product_name == "منتج"
    assert result.best.next_period_value == result.best.forecast_values[0]
