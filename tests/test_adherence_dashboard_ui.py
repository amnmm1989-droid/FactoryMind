"""
لوحة الالتزام في صفحة تخطيط الإنتاج — مدفوعة عبر AppTest.

نفس مبدأ tests/test_cold_boot.py وtests/test_column_mapping_ui.py: يشغّل
render() الحقيقي لا دالة معزولة. الفارق هنا: production_planning.py صفحة
مستقلة لا تعبر st.navigation في app.py (AppTest.switch_page يحتاج ملف
صفحة حقيقياً — لا يدعم st.Page ببناء ديناميكي كما يفعله app.py)، فتُشغَّل
عبر AppTest.from_function مباشرة.

⚠️ عزل القاعدة إلزامي هنا لا اختيارياً: بلا monkeypatch على
config.DATABASE_PATH، كل اختبار يكتب في data/app.db الحقيقية — نفس
القاعدة التي يستخدمها أي تشغيل يدوي محلي لهذا المشروع.
"""
from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest


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
    """قاعدة مؤقتة مبنية ومُعبَّأة من data.json — معزولة عن app.db الحقيقية.

    لا cold_db هنا: production_planning.py يحتاج منتجات وأشهر موجودة
    فعلاً، فالقاعدة تُبنى وتُعبَّأ (SQLiteRepository._has_data()==False ->
    migrate_from_json() تلقائياً)، لا تُترَك فارغة كما في test_cold_boot.

    ⚠️ recommendations فارغ حتى بعد التعبئة — migrate_from_json يملأ
    sales/products/months وحدها. لا "توصية مقترحة" حقيقية بلا دفعة تُشغَّل
    فعلاً؛ بلا هذا، كل خطة تُحفَظ في الاختبارات ستكون unlinked (لا
    source_recommendation_id)، ولن يُختبَر followed/overridden أصلاً.
    """
    import config
    from migrate import migrate

    db_path = str(tmp_path / "test.db")
    migrate(db_path, verbose=False)
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    return db_path


def _seed_one_recommendation(db_path: str, product_name: str, series: list[float]) -> float:
    """يحسب ويحفظ تنبؤاً وتوصية حقيقيَّين لمنتج واحد — ليس عبر run_batch
    الكامل (لا حاجة لبقية الكتالوج)، بل بنفس الخطوتين اللتين يؤدّيهما.

    Returns: الكمية الموصى بها، ليقارن الاختبار بها بدقّة (متابعة/مخالفة).
    """
    from repositories.forecast_repository import ForecastRepository
    from repositories.recommendation_repository import RecommendationRepository
    from services.decision_engine import recommend_production
    from services.forecast_engine import forecast_product

    engine_result = forecast_product(product_name, series, steps=6, use_cache=False)
    forecast_id = ForecastRepository(db_path=db_path).save_result(engine_result)
    recommendation = recommend_production(product_name, series, engine_result.best)
    RecommendationRepository(db_path=db_path).save(recommendation, forecast_id=forecast_id)
    return recommendation.recommended_quantity


def _run_page() -> AppTest:
    """يشغّل production_planning.render() على الكتالوج الحقيقي — بلا
    استيراد config/repositories هنا: from_function يحتاج الاستيراد *داخل*
    الدالة نفسها كي يُنفَّذ ضمن سياق الاختبار المعزول."""

    def script() -> None:
        from repositories.sqlite_repository import SQLiteRepository
        from ui.pages.production_planning import render

        months, products = SQLiteRepository().load_data()
        render(months, products)

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def _create_plan(at: AppTest, *, product: str, quantity: float) -> AppTest:
    """يملأ نموذج "إنشاء خطة" ويحفظه — القيمة المطلوبة عبر number_input
    مباشرة، لا عبر الكمية المقترحة، كي يُحدَّد follow/override بدقّة."""
    product_box = next(sb for sb in at.selectbox if product in sb.options)
    product_box.select(product).run()

    quantity_input = at.number_input[0]
    quantity_input.set_value(quantity).run()

    submit = next(b for b in at.button if "Save plan" in b.label)
    submit.click().run()
    assert not at.exception
    return at


def test_no_plans_yet_shows_the_none_message_not_a_crash(isolated_db):
    at = _run_page()

    captions = [c.value for c in at.caption]
    assert any("No plans linked to a recommendation yet" in c for c in captions)
    assert not any("Recommendation adherence" in h.value for h in at.subheader)


def test_a_followed_plan_reports_100_percent(isolated_db):
    """خطة تُحفَظ بنفس كمية التوصية المحسوبة فعلياً — يجب أن تُقرأ 100%."""
    from repositories.sqlite_repository import SQLiteRepository

    _, products = SQLiteRepository(db_path=isolated_db).load_data()
    product = next(iter(products))
    suggested = _seed_one_recommendation(isolated_db, product, products[product])

    at = _run_page()
    at = _create_plan(at, product=product, quantity=suggested)

    subheaders = [h.value for h in at.subheader]
    assert any("Recommendation adherence" in h for h in subheaders)
    captions = " ".join(c.value for c in at.caption)
    assert "100%" in captions


def test_an_overridden_plan_is_not_counted_as_followed(isolated_db):
    """كمية مخالفة صراحةً للمقترح المحسوب — يجب ألا تُحتسَب "متّبعة"."""
    from repositories.production_plan_repository import ProductionPlanRepository
    from repositories.sqlite_repository import SQLiteRepository

    _, products = SQLiteRepository(db_path=isolated_db).load_data()
    product = next(iter(products))
    suggested = _seed_one_recommendation(isolated_db, product, products[product])

    at = _run_page()
    # كمية بعيدة عمداً عن المقترح — لا يمكن أن تقع ضمن هامش 0.5 وحدة
    at = _create_plan(at, product=product, quantity=suggested + 500)

    stats = ProductionPlanRepository(db_path=isolated_db).adherence()
    assert stats["overridden"] == 1
    assert stats["followed"] == 0

    # النص الدقيق لا "0%" مجردة: "18.0%" في سبب توصية أخرى يحتوي "0%" كنص
    # فرعي أيضاً — بحث فضفاض كان سيمرّ حتى بلا هذا الإصلاح إطلاقاً.
    captions = " ".join(c.value for c in at.caption)
    assert "0 followed it (0%)" in captions
    assert "1 overrode it" in captions
