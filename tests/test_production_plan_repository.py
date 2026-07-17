"""
اختبارات ProductionPlanRepository.

الاختبار الأهم هنا `test_the_source_recommendation_is_recorded`: العمود
source_recommendation_id كان معرَّفاً في migration 007 بمفتاح أجنبي وتعليق
يقول إن الفصل بين recommendations و production_plans موجود ليقيس "كم مرة
تُتَّبع توصياتنا؟" — ولم يكتبه شيء قط. الصفحة تعرض التوصية ثم تحفظ القرار
بلا رابط إليها، فيبقى NULL أبداً والسؤال بلا جواب.

مرّ ذلك بلا اختبار لأن SQL الخطط كان يعيش في صفحة واجهة، ولا اختبار
لصفحة. الطبقة المفقودة هي التي تجعل الحارس ممكناً.
"""
from __future__ import annotations

import pytest

from core.exceptions import DataAccessError
from domain.entities import ProductionRecommendation, RiskScore
from repositories.production_plan_repository import (
    STATUS_CODES,
    ProductionPlanRepository,
)
from repositories.recommendation_repository import RecommendationRepository


@pytest.fixture(autouse=True)
def _clean_slate(migrated_db, repo):
    """جدولان فارغان قبل كل اختبار.

    migrated_db مشتركة للجلسة كلّها (conftest)، وadherence() تقيس مجاميع —
    فصفٌّ من اختبار سابق يغيّر جواب اختبار لاحق. الاختبارات القائمة تنجو من
    هذا لأنها لا تؤكّد إلا على ما كتبته للتوّ، لا على حالة عامة؛ وهي نجاة
    بالصدفة لا بالتصميم.

    products و months لا تُمَسّان: يملؤهما repo من data.json، والخطط تحتاج
    منتجاً وشهراً موجودين.
    """
    import sqlite3

    with sqlite3.connect(migrated_db) as conn:
        conn.execute("DELETE FROM production_plans")
        conn.execute("DELETE FROM recommendations")
        conn.commit()
    yield


@pytest.fixture
def plans(migrated_db) -> ProductionPlanRepository:
    return ProductionPlanRepository(db_path=migrated_db)


@pytest.fixture
def recommendations(migrated_db) -> RecommendationRepository:
    return RecommendationRepository(db_path=migrated_db)


@pytest.fixture
def product(repo) -> str:
    return sorted(repo.get_products())[0]


@pytest.fixture
def month_id(plans) -> int:
    return plans.month_options()[0][0]


def _recommendation(product: str, quantity: float = 100.0) -> ProductionRecommendation:
    return ProductionRecommendation(
        product_name=product,
        recommended_quantity=quantity,
        reason="اختبار",
        expected_demand_change_pct=5.0,
        risk=RiskScore(
            product_name=product, score=40, demand_volatility=0.3,
            stock_depletion_risk=None, forecast_accuracy_penalty=0.2,
            seasonality_factor=0.1, growth_rate=0.05,
        ),
    )


# ---------------------------------------------------------------------------
# الرابط المفقود
# ---------------------------------------------------------------------------
def test_the_source_recommendation_is_recorded(plans, recommendations, product, month_id):
    """العطل نفسه: خطة تُحفظ بلا أثر للتوصية التي وُلدت عنها."""
    recommendation_id = recommendations.save(_recommendation(product))

    plans.save(product, month_id, 100.0,
               source_recommendation_id=recommendation_id)

    stored = plans.all_plans()[0]
    assert stored["product"] == product
    # الرابط نفسه لا يظهر في all_plans (جدول عرض)، فنقيسه عبر ما بُني لأجله
    assert plans.adherence()["followed"] == 1


def test_following_the_recommendation_counts_as_followed(
    plans, recommendations, product, month_id
):
    recommendation_id = recommendations.save(_recommendation(product, 250.0))

    plans.save(product, month_id, 250.0, source_recommendation_id=recommendation_id)

    assert plans.adherence() == {
        "total": 1, "followed": 1, "overridden": 0, "unlinked": 0
    }


def test_overriding_the_recommendation_counts_as_overridden(
    plans, recommendations, product, month_id
):
    """السؤال الذي بُني الجدول لأجله يحتاج الطرفين: المتَّبَع والمخالَف."""
    recommendation_id = recommendations.save(_recommendation(product, 250.0))

    plans.save(product, month_id, 400.0, source_recommendation_id=recommendation_id)

    assert plans.adherence() == {
        "total": 1, "followed": 0, "overridden": 1, "unlinked": 0
    }


def test_a_plan_without_a_recommendation_is_unlinked_not_overridden(
    plans, product, month_id
):
    """None ≠ مخالفة.

    خطة لمنتج بلا توصية محسوبة قرارٌ صحيح لا نقص، وعدّها "مخالِفة" يكذب
    على من يقرأ النسبة. نفس مبدأ risk_service: المجهول يُعرَض مجهولاً.
    """
    plans.save(product, month_id, 100.0)

    assert plans.adherence() == {
        "total": 1, "followed": 0, "overridden": 0, "unlinked": 1
    }


def test_adherence_on_an_empty_table_is_zero_not_a_crash(plans):
    assert plans.adherence() == {
        "total": 0, "followed": 0, "overridden": 0, "unlinked": 0
    }


def test_the_recommendation_id_matches_the_entity(recommendations, product):
    """latest_with_id_for_product تُعيد معرّف الصف الذي تُعيد كيانه."""
    recommendations.save(_recommendation(product, 100.0))
    newest_id = recommendations.save(_recommendation(product, 999.0))

    found = recommendations.latest_with_id_for_product(product)

    assert found is not None
    stored_id, entity = found
    assert stored_id == newest_id
    assert entity.recommended_quantity == 999.0


def test_latest_for_product_still_returns_the_entity(recommendations, product):
    """التوقيع القديم لم يتغيّر — product_intelligence يعتمد عليه."""
    recommendations.save(_recommendation(product, 77.0))

    assert recommendations.latest_for_product(product).recommended_quantity == 77.0


def test_no_recommendation_gives_none(recommendations, product):
    assert recommendations.latest_with_id_for_product("لا وجود له") is None


# ---------------------------------------------------------------------------
# الحفظ
# ---------------------------------------------------------------------------
def test_saving_twice_updates_instead_of_duplicating(plans, product, month_id):
    """UNIQUE(product_id, month_id) -> خطة واحدة لكل منتج/شهر."""
    plans.save(product, month_id, 100.0, notes="أولى")
    plans.save(product, month_id, 200.0, notes="ثانية")

    stored = plans.all_plans()
    assert len(stored) == 1
    assert stored[0]["planned_quantity"] == 200.0
    assert stored[0]["notes"] == "ثانية"


def test_an_update_rewrites_the_source_link(plans, recommendations, product, month_id):
    """الخطة المعدَّلة تحمل التوصية التي رآها المخطِّط ساعة التعديل.

    لولا source_recommendation_id في جملة DO UPDATE، لبقي الرابط الأول
    ملتصقاً بكمية جديدة لم تُشتقّ منه — أسوأ من غيابه، لأنه يبدو صحيحاً.
    """
    first = recommendations.save(_recommendation(product, 100.0))
    plans.save(product, month_id, 100.0, source_recommendation_id=first)
    assert plans.adherence()["followed"] == 1

    second = recommendations.save(_recommendation(product, 500.0))
    plans.save(product, month_id, 500.0, source_recommendation_id=second)

    assert plans.adherence() == {
        "total": 1, "followed": 1, "overridden": 0, "unlinked": 0
    }


def test_an_unknown_product_is_refused_clearly(plans, month_id):
    with pytest.raises(DataAccessError) as caught:
        plans.save("منتج لا وجود له", month_id, 10.0)

    assert "منتج لا وجود له" in str(caught.value)


def test_an_invalid_status_is_refused_before_sqlite(plans, product, month_id):
    """الرفض برسالة مفهومة، لا بارتطام بقيد CHECK."""
    with pytest.raises(DataAccessError) as caught:
        plans.save(product, month_id, 10.0, status="ملغاة_ربما")

    assert "ملغاة_ربما" in str(caught.value)
    assert plans.all_plans() == []


@pytest.mark.parametrize("status", STATUS_CODES)
def test_every_declared_status_is_accepted_by_the_schema(
    plans, product, month_id, status
):
    """القائمة في بايثون مكرَّرة عن قيد CHECK في 007 — والتكرار ينحرف.

    لو أضيفت حالة هنا ولم تُضَف هناك، يمرّ الاختبار الوحدوي وتنفجر القاعدة
    عند أول حفظ حقيقي.
    """
    plans.save(product, month_id, 10.0, status=status)

    assert plans.all_plans()[0]["status"] == status


def test_notes_left_empty_are_stored_as_null_not_empty_string(
    plans, product, month_id
):
    plans.save(product, month_id, 10.0, notes="")

    assert plans.all_plans()[0]["notes"] is None


def test_the_page_holds_no_sql():
    """الخرق نفسه: صفحة واجهة تفتح اتصالها وتكتب استعلاماتها.

    كانت production_planning وحدها بين الصفحات الخمس تفعل ذلك — وهو ما
    أخفى إغفال source_recommendation_id: استعلامٌ كتبه من يفكّر في الشاشة
    لا في الجدول، بلا عقد ولا اختبار.
    """
    from pathlib import Path

    source = Path("ui/pages/production_planning.py").read_text(encoding="utf-8")

    assert "sqlite3" not in source
    for keyword in ("INSERT INTO", "SELECT ", "UPDATE ", "DELETE FROM"):
        assert keyword not in source, f"SQL خام عاد إلى الصفحة: {keyword}"
