# tests/test_validation.py
"""
تقرير التحقّق — الرقم الذي يُعرَض على مصنع.

أخطر ما يمكن أن يكذب هنا هو **تسريب المستقبل**: لو رأى التدريب ولو نقطة
واحدة من نافذة الاختبار، لبدت الدقّة ممتازة وهي وهم — وذلك أسوأ من عدم
وجود التقرير أصلاً، لأنه يبيع ثقةً لا أساس لها.
"""
from __future__ import annotations

import numpy as np
import pytest

from services.validation import (
    MIN_TRAIN_POINTS,
    ValidationReport,
    _origins_for,
    build_validation_report,
    validate_product,
)

# سلسلة منتظمة طويلة — تكفي عدة أصول
STEADY = [100.0 + (i % 5) * 10 for i in range(40)]
INTERMITTENT = [0.0, 0.0, 0.0, 60.0] * 10
TOO_SHORT = [5.0, 7.0, 6.0]


# ---------------------------------------------------------------------------
# مواضع الأصول
# ---------------------------------------------------------------------------
def test_origins_step_by_a_full_horizon_so_windows_do_not_overlap():
    """نوافذ متداخلة تحتسب الخطأ نفسه مرتين فيبدو الثبات أعلى مما هو."""
    positions = _origins_for(length=40, horizon=3, requested=3)

    assert positions == [31, 34, 37]


def test_origins_stop_before_starving_the_training_window():
    positions = _origins_for(length=20, horizon=3, requested=10)

    assert all(p >= MIN_TRAIN_POINTS for p in positions)


def test_a_series_too_short_yields_no_origin():
    assert _origins_for(length=6, horizon=3, requested=3) == []


# ---------------------------------------------------------------------------
# لا تسريب للمستقبل — الضمانة التي يقوم عليها التقرير كله
# ---------------------------------------------------------------------------
def test_training_never_sees_the_window_it_is_judged_on(monkeypatch):
    """يعترض المحرك ويسجّل ما رآه فعلاً في كل أصل.

    لو مُرِّرت السلسلة كاملة (أو أي جزء من نافذة الاختبار)، لالتقطه هذا.
    """
    import services.validation as validation

    seen: list[list[float]] = []
    real = validation.forecast_product

    def spy(product_name, series, **kwargs):
        seen.append(list(series))
        return real(product_name, series, **kwargs)

    monkeypatch.setattr(validation, "forecast_product", spy)
    result = validate_product("منتج", STEADY, horizon=3, origins=3)

    assert len(seen) == result.origins_tested
    for train, origin in zip(seen, result.origins):
        # التدريب هو بالضبط بداية السلسلة حتى الأصل — لا نقطة بعده
        assert train == STEADY[:origin.train_size]
        assert len(train) == origin.train_size


def test_each_origin_is_judged_on_the_periods_that_followed_it():
    result = validate_product("منتج", STEADY, horizon=3, origins=2)

    for origin in result.origins:
        expected = STEADY[origin.train_size:origin.train_size + 3]
        assert origin.actual == expected


# ---------------------------------------------------------------------------
# المقاييس
# ---------------------------------------------------------------------------
def test_a_perfect_forecast_scores_zero_wape(monkeypatch):
    """حارس اتجاه المقياس: 0% خطأ لا 100%."""
    import services.validation as validation

    class _Perfect:
        def __init__(self, values): self.forecast_values = values

    class _Result:
        best_model_name = "Oracle"
        def __init__(self, values): self.best = _Perfect(values)

    def oracle(product_name, series, *, steps, **kwargs):
        start = len(series)
        return _Result(STEADY[start:start + steps])

    monkeypatch.setattr(validation, "forecast_product", oracle)
    result = validate_product("منتج", STEADY, horizon=3, origins=2)

    assert result.wape == pytest.approx(0.0)
    assert result.mase == pytest.approx(0.0)


def test_beat_naive_compares_on_the_same_window_and_horizon():
    """العدالة شرط في رقمٍ يُعرَض على مصنع.

    مقام MASE هو خطأ الساذج *بخطوة واحدة داخل التدريب*؛ محاسبة تنبؤٍ
    بأفق ثلاث فترات به تحاسبه على صعوبة الأفق لا على جودته. لذا يقارن
    beat_naive بساذجٍ شُغِّل على **نفس النافذة ونفس الأفق**.
    """
    result = validate_product("منتج", STEADY, horizon=3, origins=3)

    assert result.mae is not None and result.naive_mae is not None
    assert result.beat_naive is (result.mae < result.naive_mae)


def test_the_naive_benchmark_repeats_the_last_training_value():
    result = validate_product("منتج", STEADY, horizon=3, origins=2)

    for origin in result.origins:
        expected = STEADY[origin.train_size - 1]
        assert origin.naive == [expected] * len(origin.actual)


def test_beat_naive_is_unknown_when_there_was_no_demand():
    dormant = [40.0, 50.0, 45.0, 55.0, 48.0] * 4 + [0.0] * 12

    result = validate_product("راكد", dormant, horizon=3, origins=3)

    assert result.mae is None and result.naive_mae is None
    assert result.beat_naive is None


def test_metrics_are_pooled_across_origins_not_averaged_per_origin():
    """أصلٌ بقيم صغيرة يجب ألا يقلب النتيجة — نفس مبدأ WAPE في المحرك."""
    result = validate_product("منتج", STEADY, horizon=3, origins=3)

    pooled_actual = [v for origin in result.origins for v in origin.actual]
    pooled_predicted = [v for origin in result.origins for v in origin.predicted]
    expected = (
        np.sum(np.abs(np.array(pooled_actual) - np.array(pooled_predicted)))
        / np.sum(np.abs(pooled_actual)) * 100
    )

    assert result.wape == pytest.approx(expected)


# ---------------------------------------------------------------------------
# الأمانة: ما لا يمكن تقييمه يُذكر لا يُحذف
# ---------------------------------------------------------------------------
def test_a_series_too_short_is_refused_loudly():
    with pytest.raises(ValueError, match="لا تكفي"):
        validate_product("قصير", TOO_SHORT, horizon=3, origins=3)


def test_unevaluable_products_are_named_not_dropped():
    report = build_validation_report(
        {"جيد": STEADY, "قصير": TOO_SHORT}, horizon=3, origins=2
    )

    assert [name for name, _ in report.skipped] == ["قصير"]
    assert report.evaluated_count == 1
    assert report.total_count == 2


def test_a_zero_demand_window_is_not_reported_as_perfect_accuracy():
    """الفخّ الحقيقي على بيانات متقطّعة، وقد وقع فعلاً قبل هذا الحارس.

    منتج نافذة اختباره أصفار بالكامل، والنموذج يتنبّأ بصفر -> MASE = 0.00
    أي "دقّة مثالية". قِيس: 19 من 40 منتجاً أسبوعياً. عرض ذلك على مصنع
    يبيع ثقةً بلا أساس.
    """
    dormant = [40.0, 50.0, 45.0, 55.0, 48.0] * 4 + [0.0] * 12

    result = validate_product("راكد", dormant, horizon=3, origins=3)

    assert all(sum(abs(v) for v in o.actual) == 0 for o in result.origins)
    assert result.wape is None
    assert result.mase is None, "نافذة بلا طلب لا تُنتج دقّة، مثاليةً كانت أو غيرها"
    assert result.beat_naive is None


def test_products_without_demand_do_not_inflate_coverage():
    """شُغِّلت عليها الأداة، لكن لا شيء قِيس — فلا تُحتسب تغطيةً."""
    dormant = [40.0, 50.0, 45.0, 55.0, 48.0] * 4 + [0.0] * 12

    report = build_validation_report(
        {"حيّ": STEADY, "راكد": dormant}, horizon=3, origins=3
    )

    assert report.evaluated_count == 2      # كلاهما شُغِّل
    assert report.measured_count == 1       # واحد فقط قِيس
    assert report.no_demand_count == 1
    assert report.coverage == pytest.approx(0.5)


def test_medians_ignore_the_unmeasurable_rather_than_scoring_them_zero():
    dormant = [40.0, 50.0, 45.0, 55.0, 48.0] * 4 + [0.0] * 12

    report = build_validation_report(
        {"حيّ": STEADY, "راكد": dormant}, horizon=3, origins=3
    )
    live = next(p for p in report.products if p.product_name == "حيّ")

    assert report.median_wape == pytest.approx(live.wape)
    assert report.median_mase == pytest.approx(live.mase)


def test_coverage_counts_the_skipped_in_its_denominator():
    """النسبة جزء من النتيجة لا هامش عليها: حذف المتعذّر يجمّل المتوسط."""
    report = build_validation_report(
        {"a": STEADY, "b": STEADY, "c": TOO_SHORT, "d": TOO_SHORT},
        horizon=3, origins=2,
    )

    assert report.coverage == pytest.approx(0.5)


def test_an_empty_catalogue_reports_zero_coverage_without_dividing_by_zero():
    report = build_validation_report({}, horizon=3, origins=2)

    assert report.coverage == 0.0
    assert report.median_wape is None
    assert report.beat_naive_share is None


# ---------------------------------------------------------------------------
# التجميع على مستوى الكتالوج
# ---------------------------------------------------------------------------
def test_the_report_records_which_models_the_tool_actually_chose():
    """ما اختارته الأداة عبر الزمن — لا ما نظنّه سيفوز."""
    report = build_validation_report({"a": STEADY, "b": INTERMITTENT},
                                     horizon=3, origins=2)

    assert sum(report.model_usage.values()) == sum(
        p.origins_tested for p in report.products
    )


def test_intermittent_products_are_labelled_by_their_class():
    report = build_validation_report({"متقطّع": INTERMITTENT}, horizon=3, origins=2)

    assert report.products[0].demand_class in ("intermittent", "lumpy")


def test_progress_is_reported_for_every_product():
    seen = []
    build_validation_report(
        {"a": STEADY, "b": TOO_SHORT}, horizon=3, origins=2,
        on_progress=lambda done, total, name: seen.append((done, total)),
    )

    assert seen == [(1, 2), (2, 2)]


def test_report_defaults_are_sane():
    report = ValidationReport()

    assert report.coverage == 0.0
    assert report.model_usage == {}
