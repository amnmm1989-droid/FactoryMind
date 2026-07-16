# tests/test_recommendation_repository.py
"""
اختبارات حفظ التوصيات (Phase 4) في جدول recommendations (Phase 2).
"""
from __future__ import annotations

import pytest

from core.exceptions import DataAccessError
from domain.entities import ForecastResult, InventoryStatus, RiskLevel
from repositories.recommendation_repository import RecommendationRepository
from services.decision_engine import recommend_production

STEADY = [100.0] * 30


def _forecast(values=None, mape=10.0) -> ForecastResult:
    return ForecastResult(
        product_name="منتج",
        model_name="Naive",
        forecast_values=values if values is not None else [120.0] * 6,
        lower_bound=[100.0] * 6,
        upper_bound=[140.0] * 6,
        mae=4.0,
        rmse=5.0,
        mape=mape,
    )


@pytest.fixture
def rec_repo(repo, migrated_db) -> RecommendationRepository:
    return RecommendationRepository(db_path=migrated_db)


@pytest.fixture
def product_name(repo) -> str:
    return repo.get_products()[0]


@pytest.fixture
def recommendation(product_name):
    return recommend_production(product_name, STEADY, _forecast())


# ---------------------------------------------------------------------------
# الحفظ والاسترجاع
# ---------------------------------------------------------------------------
def test_save_returns_an_id(rec_repo, recommendation):
    assert rec_repo.save(recommendation) > 0


def test_recommendation_round_trips(rec_repo, recommendation, product_name):
    rec_repo.save(recommendation)

    stored = rec_repo.latest_for_product(product_name)

    assert stored is not None
    assert stored.recommended_quantity == recommendation.recommended_quantity
    assert stored.reason == recommendation.reason
    assert stored.product_name == product_name


def test_risk_factors_round_trip(rec_repo, recommendation, product_name):
    rec_repo.save(recommendation)

    stored = rec_repo.latest_for_product(product_name)

    assert stored.risk is not None
    assert stored.risk.score == pytest.approx(recommendation.risk.score)
    assert stored.risk.demand_volatility == pytest.approx(
        recommendation.risk.demand_volatility
    )


def test_unknown_factor_survives_as_null_not_zero(rec_repo, recommendation, product_name):
    """جوهر Phase 4: None يعبر قاعدة البيانات ويعود None.

    لو خزّنّاه 0.0، لعاد منتج مجهول المخزون من القاعدة وكأن مخزونه وفير.
    """
    assert recommendation.risk.stock_depletion_risk is None
    rec_repo.save(recommendation)

    stored = rec_repo.latest_for_product(product_name)

    assert stored.risk.stock_depletion_risk is None
    assert "stock_depletion_risk" in stored.risk.missing_factors


def test_latest_returns_the_newest(rec_repo, product_name):
    rec_repo.save(recommend_production(product_name, STEADY, _forecast(values=[50.0] * 6)))
    rec_repo.save(recommend_production(product_name, STEADY, _forecast(values=[999.0] * 6)))

    stored = rec_repo.latest_for_product(product_name)

    assert stored.recommended_quantity == 999.0


def test_latest_is_none_before_anything_is_saved(rec_repo, repo):
    untouched = repo.get_products()[11]

    assert rec_repo.latest_for_product(untouched) is None


def test_history_keeps_every_round(rec_repo, product_name):
    for _ in range(3):
        rec_repo.save(recommend_production(product_name, STEADY, _forecast()))

    history = rec_repo.history_for_product(product_name)

    assert len(history) >= 3


def test_forecast_id_links_the_recommendation_to_its_source(rec_repo, recommendation, product_name):
    """الأثر الذي يجيب 'لماذا أوصى النظام بهذا الرقم؟'"""
    import sqlite3

    from repositories.forecast_repository import ForecastRepository
    from services.forecast_engine import forecast_product
    from services.forecast_engine.naive import NaiveForecaster

    engine_result = forecast_product(
        product_name, STEADY, steps=6, models=[NaiveForecaster()], use_cache=False
    )
    forecast_id = ForecastRepository(db_path=rec_repo.db_path).save_result(engine_result)

    rec_repo.save(recommendation, forecast_id=forecast_id)

    conn = sqlite3.connect(rec_repo.db_path)
    try:
        stored = conn.execute(
            "SELECT forecast_id FROM recommendations ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
    finally:
        conn.close()
    assert stored == forecast_id


def test_unknown_product_is_rejected(rec_repo, recommendation):
    from dataclasses import replace

    orphan = replace(recommendation, product_name="لا وجود له")

    with pytest.raises(DataAccessError, match="منتج غير موجود"):
        rec_repo.save(orphan)


# ---------------------------------------------------------------------------
# قائمة الأعلى خطورة — شاشة "ما الذي يحتاج انتباهي؟"
# ---------------------------------------------------------------------------
def test_highest_risk_is_ordered_descending(rec_repo, repo):
    volatile = [10.0, 200.0, 5.0, 180.0] * 8
    for name in repo.get_products()[:3]:
        rec_repo.save(recommend_production(name, volatile, _forecast(mape=70.0)))
    for name in repo.get_products()[3:6]:
        rec_repo.save(recommend_production(name, STEADY, _forecast(mape=1.0)))

    top = rec_repo.highest_risk(limit=6)

    scores = [r.risk.score for r in top]
    assert scores == sorted(scores, reverse=True)


def test_highest_risk_respects_the_limit(rec_repo, repo):
    for name in repo.get_products()[:5]:
        rec_repo.save(recommend_production(name, STEADY, _forecast()))

    assert len(rec_repo.highest_risk(limit=2)) == 2


def test_highest_risk_shows_one_row_per_product(rec_repo, product_name):
    """ثلاث توصيات لمنتج واحد لا تعني ثلاثة منتجات في قائمة الانتباه."""
    for _ in range(3):
        rec_repo.save(recommend_production(product_name, STEADY, _forecast()))

    top = rec_repo.highest_risk(limit=10)

    names = [r.product_name for r in top]
    assert names.count(product_name) == 1


def test_products_without_a_risk_score_are_excluded(rec_repo, product_name):
    """قائمة 'الأعلى خطورة' التي تضم منتجاً لم تُحسب خطورته تكذب على قارئها."""
    import sqlite3

    rec_repo.save(recommend_production(product_name, STEADY, _forecast()))
    conn = sqlite3.connect(rec_repo.db_path)
    try:
        conn.execute("UPDATE recommendations SET risk_score = NULL")
        conn.commit()
    finally:
        conn.close()

    assert rec_repo.highest_risk(limit=10) == []


def test_stored_risk_level_matches_the_score(rec_repo, product_name):
    volatile = [10.0, 200.0, 5.0, 180.0] * 8
    rec_repo.save(recommend_production(product_name, volatile, _forecast(mape=80.0)))

    stored = rec_repo.latest_for_product(product_name)

    assert stored.risk.level == RiskLevel.from_score(stored.risk.score)
