# tests/test_forecast_repository.py
"""
اختبارات حفظ نتائج المحرك (Phase 3) في جداول Phase 2.

يعتمد على تجهيزتَي conftest: `repo` (يملأ المنتجات من data.json) و
`migrated_db` (قاعدة مؤقتة طُبِّقت عليها الـ migrations).
"""
from __future__ import annotations

import json
import math

import pytest

from core.exceptions import DataAccessError
from repositories.forecast_repository import ForecastRepository
from services.forecast_engine import forecast_product
from services.forecast_engine.naive import MovingAverageForecaster, NaiveForecaster

SERIES = [100 + 30 * math.sin(i * math.pi / 6) + i for i in range(48)]


@pytest.fixture
def forecast_repo(repo, migrated_db) -> ForecastRepository:
    """مستودع التنبؤات على القاعدة المؤقتة. `repo` يضمن وجود المنتجات."""
    return ForecastRepository(db_path=migrated_db)


@pytest.fixture
def product_name(repo) -> str:
    return repo.get_products()[0]


@pytest.fixture
def result(product_name):
    """حصيلة محرك بنموذجين سريعين — الاختبار هنا للتخزين لا للتنبؤ."""
    return forecast_product(
        product_name, SERIES, steps=6,
        models=[NaiveForecaster(), MovingAverageForecaster()], use_cache=False,
    )


# ---------------------------------------------------------------------------
# الحفظ
# ---------------------------------------------------------------------------
def test_save_returns_a_forecast_id(forecast_repo, result):
    forecast_id = forecast_repo.save_result(result)

    assert forecast_id > 0


def test_saved_forecast_round_trips(forecast_repo, result, product_name):
    forecast_repo.save_result(result)

    stored = forecast_repo.latest_forecast(product_name)

    assert stored is not None
    assert stored["model_name"] == result.best_model_name
    assert stored["forecast_values"] == result.best.forecast_values
    assert stored["horizon"] == 6


def test_save_records_every_model_not_only_the_winner(forecast_repo, result, product_name):
    """جدول model_performance يجيب 'لماذا هذا النموذج؟' — والجواب يحتاج الخاسرين."""
    forecast_repo.save_result(result)

    ranking = forecast_repo.model_ranking(product_name)

    assert len(ranking) == len(result.evaluations)
    assert {row["model_name"] for row in ranking} == {
        e.model_name for e in result.evaluations
    }


def test_exactly_one_model_is_marked_best(forecast_repo, result, product_name):
    forecast_repo.save_result(result)

    ranking = forecast_repo.model_ranking(product_name)

    best = [row for row in ranking if row["is_best"] == 1]
    assert len(best) == 1
    assert best[0]["model_name"] == result.best_model_name


def test_ranking_is_ordered_by_accuracy(forecast_repo, result, product_name):
    forecast_repo.save_result(result)

    ranking = forecast_repo.model_ranking(product_name)

    scored = [row["rmse"] for row in ranking if row["rmse"] is not None]
    assert scored == sorted(scored)


def test_repeated_saves_do_not_blur_the_rounds(forecast_repo, product_name):
    """انحدار: model_performance تاريخي، فتقييم نفس المنتج مرتين يُراكم صفوفاً.

    الحصر بـ data_hash كان يطابق كل الجولات (نفس البيانات = نفس البصمة)،
    فيُرجع ranking عدة نماذج بـ is_best=1 — كل واحد فائز جولةٍ مختلفة.
    النطاق الآن forecast_id: جولة واحدة، فائز واحد.
    """
    first = forecast_product(
        product_name, SERIES, steps=6, models=[NaiveForecaster()], use_cache=False
    )
    forecast_repo.save_result(first)
    second = forecast_product(
        product_name, SERIES, steps=6,
        models=[NaiveForecaster(), MovingAverageForecaster()], use_cache=False,
    )
    forecast_repo.save_result(second)

    ranking = forecast_repo.model_ranking(product_name)

    assert len(ranking) == 2  # نماذج الجولة الأخيرة فقط
    assert len([row for row in ranking if row["is_best"] == 1]) == 1


def test_history_is_retained_across_rounds(forecast_repo, product_name):
    """الجولة السابقة لا تُمحى — تتبّع الأداء عبر الزمن هو غرض الجدول."""
    import sqlite3

    for _ in range(3):
        forecast_repo.save_result(
            forecast_product(
                product_name, SERIES, steps=6, models=[NaiveForecaster()], use_cache=False
            )
        )

    conn = sqlite3.connect(forecast_repo.db_path)
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM model_performance mp JOIN products p "
            "ON mp.product_id = p.id WHERE p.name = ?", (product_name,)
        ).fetchone()[0]
    finally:
        conn.close()

    assert total >= 3  # كل جولة تركت أثرها


def test_data_hash_is_stored_with_the_forecast(forecast_repo, result, product_name):
    """يربط التنبؤ بالبيانات التي وُلّد منها — أساس صلاحية الـ cache."""
    forecast_repo.save_result(result)

    stored = forecast_repo.latest_forecast(product_name)

    assert stored["data_hash"] == result.data_hash


def test_saving_an_unknown_product_is_rejected(forecast_repo, result):
    """مفتاح أجنبي غير موجود — يجب أن يفشل صراحةً لا أن يُخزَّن يتيماً."""
    from dataclasses import replace

    orphan = replace(result, product_name="منتج لا وجود له")

    with pytest.raises(DataAccessError, match="منتج غير موجود"):
        forecast_repo.save_result(orphan)


def test_a_failed_save_leaves_nothing_behind(forecast_repo, result, product_name):
    """الذرّية: تنبؤ بلا سجل تقييم = توصية لا نعرف أساسها."""
    from dataclasses import replace

    before = forecast_repo.latest_forecast(product_name)
    orphan = replace(result, product_name="منتج لا وجود له")

    with pytest.raises(DataAccessError):
        forecast_repo.save_result(orphan)

    assert forecast_repo.latest_forecast(product_name) == before


# ---------------------------------------------------------------------------
# القراءة
# ---------------------------------------------------------------------------
def test_latest_forecast_is_none_before_anything_is_saved(forecast_repo, repo):
    untouched = repo.get_products()[7]

    assert forecast_repo.latest_forecast(untouched) is None


def test_latest_forecast_returns_the_newest(forecast_repo, product_name):
    first = forecast_product(
        product_name, SERIES, steps=3, models=[NaiveForecaster()], use_cache=False
    )
    forecast_repo.save_result(first)
    second = forecast_product(
        product_name, SERIES, steps=12, models=[MovingAverageForecaster()], use_cache=False
    )
    forecast_repo.save_result(second)

    stored = forecast_repo.latest_forecast(product_name)

    assert stored["horizon"] == 12
    assert stored["model_name"] == "MovingAverage"


def test_find_cached_matches_on_identical_data(forecast_repo, result, product_name):
    forecast_repo.save_result(result)

    found = forecast_repo.find_cached(product_name, result.data_hash)

    assert found is not None
    assert found["model_name"] == result.best_model_name


def test_find_cached_misses_when_the_data_changed(forecast_repo, result, product_name):
    """بصمة مختلفة = بيانات مختلفة = التنبؤ القديم لا يعني شيئاً."""
    forecast_repo.save_result(result)

    assert forecast_repo.find_cached(product_name, "بصمة-مختلفة") is None


def test_forecast_values_are_stored_as_valid_json(forecast_repo, result, product_name):
    """قيد json_valid في migration 004 — نتحقق أنه ليس حبراً على ورق."""
    import sqlite3

    forecast_repo.save_result(result)
    conn = sqlite3.connect(forecast_repo.db_path)
    try:
        raw = conn.execute("SELECT forecast_values FROM forecasts LIMIT 1").fetchone()[0]
    finally:
        conn.close()

    assert isinstance(json.loads(raw), list)
