# tests/test_batch.py
"""
اختبارات خدمة الدفعة (Phase 6).

المحور: الدفعة هي ما يجعل الصفحة التنفيذية ممكنة أصلاً. منتج واحد فاشل
يجب ألا يُسقط الكتالوج، والنتائج يجب أن تصل الجداول فعلاً.
"""
from __future__ import annotations

import math

import pytest

from repositories.forecast_repository import ForecastRepository
from repositories.recommendation_repository import RecommendationRepository
from services.batch import fast_models, run_batch

STEADY = [100.0 + (i % 5) for i in range(30)]
INTERMITTENT = [0.0, 0.0, 40.0] * 10


@pytest.fixture
def catalogue(repo) -> dict[str, list[float]]:
    """ثلاثة منتجات حقيقية من القاعدة — المفاتيح الأجنبية تتطلب وجودها."""
    names = repo.get_products()[:3]
    return {
        names[0]: STEADY,
        names[1]: INTERMITTENT,
        names[2]: [0.0] * 30,  # بلا مبيعات — يجب أن يفشل بلا إسقاط الدفعة
    }


def test_batch_reports_totals(catalogue, migrated_db):
    report = run_batch(catalogue, db_path=migrated_db)

    assert report.total == 3
    assert report.succeeded + report.failure_count == 3


def test_a_dead_product_fails_without_killing_the_batch(catalogue, migrated_db):
    """منتج بلا مبيعات لا ينطبق عليه نموذج — متوقَّع لا عطل."""
    report = run_batch(catalogue, db_path=migrated_db)

    assert report.succeeded == 2
    assert report.failure_count == 1


def test_failures_carry_a_reason(catalogue, migrated_db):
    report = run_batch(catalogue, db_path=migrated_db)

    name, reason = report.failed[0]
    assert name in catalogue
    assert reason


def test_batch_persists_forecasts(catalogue, migrated_db):
    run_batch(catalogue, db_path=migrated_db)

    stored = ForecastRepository(db_path=migrated_db).latest_forecast(
        list(catalogue)[0]
    )
    assert stored is not None
    assert stored["horizon"] == 6


def test_batch_persists_recommendations(catalogue, migrated_db):
    run_batch(catalogue, db_path=migrated_db)

    stored = RecommendationRepository(db_path=migrated_db).latest_for_product(
        list(catalogue)[0]
    )
    assert stored is not None
    assert stored.risk is not None


def test_batch_links_recommendation_to_its_forecast(catalogue, migrated_db):
    """الأثر الذي يجيب 'لماذا أوصى النظام بهذا؟' — يجب ألا تكسره الدفعة."""
    import sqlite3

    run_batch(catalogue, db_path=migrated_db)

    conn = sqlite3.connect(migrated_db)
    try:
        orphans = conn.execute(
            "SELECT COUNT(*) FROM recommendations WHERE forecast_id IS NULL"
        ).fetchone()[0]
    finally:
        conn.close()
    assert orphans == 0


def test_progress_is_reported_for_every_product(catalogue, migrated_db):
    seen = []

    run_batch(catalogue, db_path=migrated_db,
              on_progress=lambda done, total, name: seen.append((done, total)))

    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_progress_includes_failures(catalogue, migrated_db):
    """شريط التقدّم يجب أن يصل 100% حتى لو فشل منتج."""
    seen = []

    run_batch(catalogue, db_path=migrated_db,
              on_progress=lambda done, total, name: seen.append(done))

    assert seen[-1] == 3


def test_batch_records_elapsed_time(catalogue, migrated_db):
    report = run_batch(catalogue, db_path=migrated_db)

    assert report.elapsed_seconds > 0
    assert math.isfinite(report.elapsed_seconds)


def test_fast_models_exclude_the_heavy_family():
    """سبب وجود الوضع السريع: 9 نماذج × كتالوج كامل = دقائق لا ثوانٍ."""
    names = {m.name for m in fast_models()}

    assert names == {"Naive", "MovingAverage", "Croston", "TSB"}
    assert not names & {"Prophet", "XGBoost", "RandomForest", "ETS", "SARIMA"}


def test_batch_is_rerunnable(catalogue, migrated_db):
    """إعادة الحساب من الواجهة لا يجب أن تفشل على بيانات موجودة."""
    first = run_batch(catalogue, db_path=migrated_db)
    second = run_batch(catalogue, db_path=migrated_db)

    assert second.succeeded == first.succeeded


def test_rerun_leaves_one_recommendation_per_product_on_top(catalogue, migrated_db):
    """جدول التوصيات تاريخي — لكن الصفحة التنفيذية تعرض الأحدث فقط."""
    run_batch(catalogue, db_path=migrated_db)
    run_batch(catalogue, db_path=migrated_db)

    top = RecommendationRepository(db_path=migrated_db).highest_risk(limit=50)

    names = [r.product_name for r in top]
    assert len(names) == len(set(names))
