# tests/test_calibration_ui.py
"""
معايرة أوزان الخطورة على صفحة تخطيط الإنتاج — مدفوعة عبر AppTest.

نفس تقنية tests/test_actuals_upload_ui.py: صفحة مستقلة لا تعبر
st.navigation في app.py، فتُشغَّل عبر AppTest.from_function مباشرة.
البيانات تُزرَع مباشرة عبر المستودعات — لا حاجة لعبور واجهة الرفع لبناء
عيّنة المعايرة، فالقسم يقرأ plans.validated_outcomes() عند كل تصيير.
"""
from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from services.risk_service.calibration import MIN_SAMPLE_PER_FACTOR


@pytest.fixture(autouse=True)
def _isolate_streamlit_caches():
    import streamlit as st

    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    import config
    from migrate import migrate

    db_path = str(tmp_path / "test.db")
    migrate(db_path, verbose=False)
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    return db_path


def _run_page() -> AppTest:
    def script() -> None:
        from repositories.sqlite_repository import SQLiteRepository
        from ui.pages.production_planning import render

        months, products = SQLiteRepository().load_data()
        render(months, products)

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def _recommendation(product: str, demand_volatility: float):
    from domain.entities import ProductionRecommendation, RiskScore

    return ProductionRecommendation(
        product_name=product,
        recommended_quantity=100.0,
        reason="اختبار",
        expected_demand_change_pct=5.0,
        risk=RiskScore(
            product_name=product, score=40, demand_volatility=demand_volatility,
            stock_depletion_risk=None, forecast_accuracy_penalty=0.2,
            seasonality_factor=0.1, growth_rate=0.05,
        ),
    )


def _seed_validated_outcomes(db_path: str, count: int) -> None:
    """يزرع count خطة، كل واحدة لمنتج/شهر مختلفين، بعامل demand_volatility
    مرتفعاً كلما ارتفع خطأ التخطيط — نفس بناء test_calibration.py."""
    from repositories.production_plan_repository import ProductionPlanRepository
    from repositories.recommendation_repository import RecommendationRepository
    from repositories.sqlite_repository import SQLiteRepository

    _, products = SQLiteRepository(db_path=db_path).load_data()
    plans = ProductionPlanRepository(db_path=db_path)
    recommendations = RecommendationRepository(db_path=db_path)
    month_options = plans.month_options()
    product_names = list(products)

    for i in range(count):
        product = product_names[i % len(product_names)]
        month_id, month_label = month_options[i % len(month_options)]
        demand_volatility = float(i)
        recommendation_id = recommendations.save(
            _recommendation(product, demand_volatility)
        )
        plans.save(product, month_id, 100.0, source_recommendation_id=recommendation_id)
        plans.record_actuals([month_label], {product: [100.0 - i]})


def test_too_few_validated_plans_shows_the_none_message(isolated_db):
    at = _run_page()

    captions = " ".join(c.value for c in at.caption)
    assert "not enough yet to test any factor" in captions


def test_enough_validated_plans_shows_the_calibration_table(isolated_db):
    _seed_validated_outcomes(isolated_db, MIN_SAMPLE_PER_FACTOR + 5)

    at = _run_page()

    subheaders = " ".join(h.value for h in at.subheader)
    assert "Risk weight calibration" in subheaders
    assert len(at.dataframe) >= 1


def test_the_predictive_factor_gets_a_suggested_weight(isolated_db):
    """demand_volatility مبني ليرتفع تماماً مع خطأ التخطيط — يجب أن يظهر
    له وزن مقترَح رقمياً، لا شرطة "غير مُختبَر"."""
    _seed_validated_outcomes(isolated_db, MIN_SAMPLE_PER_FACTOR + 5)

    at = _run_page()

    calibration_frame = next(
        df.value for df in at.dataframe if "Demand volatility" in df.value.to_string()
    )
    row = calibration_frame[calibration_frame["Factor"] == "Demand volatility"].iloc[0]
    assert row["Suggested weight"] != "—"
