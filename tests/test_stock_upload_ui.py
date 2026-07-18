# tests/test_stock_upload_ui.py
"""
رفع ملف المخزون (Roadmap "Stock file" — سابقة 2.c) — مدفوعة عبر AppTest.

نفس مبدأ tests/test_column_mapping_ui.py: يشغّل app.py الحقيقي عبر
AppTest.from_file لا صفحة معزولة، لأن التسلسل (رفع → قراءة → خصم من
التوصية المحفوظة عبر الدفعة) يعبر st.session_state وrun_batch معاً —
لا يُختبَر بمعزل عن Streamlit فعلياً.

⚠️ عزل القاعدة إلزامي هنا (نفس نمط isolated_db أدناه): بلا monkeypatch
على config.DATABASE_PATH، الحساب يكتب في data/app.db الحقيقية.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")

STOCK_CSV = "Product,Current Stock\n{product},5\n"


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


def _boot() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def _upload_stock(at: AppTest, product: str) -> AppTest:
    content = STOCK_CSV.format(product=product).encode("utf-8")
    # [0] = أداة رفع المبيعات، [1] = أداة رفع المخزون — تُعرض الثانية دوماً
    # بعد الأولى في render_upload_widget() (راجع ui/data_source.py).
    at.sidebar.file_uploader[1].set_value([("stock.csv", content, "text/csv")])
    at.run()
    assert not at.exception
    return at


def _recompute(at: AppTest) -> AppTest:
    button = next(b for b in at.sidebar.button if "Compute catalogue" in b.label)
    button.click().run()
    at.run()
    assert not at.exception
    return at


def test_uploading_a_stock_file_shows_a_success_message(isolated_db):
    from repositories.sqlite_repository import SQLiteRepository

    _, products = SQLiteRepository(db_path=isolated_db).load_data()
    product = next(iter(products))

    at = _boot()
    at = _upload_stock(at, product)

    messages = " ".join(s.value for s in at.sidebar.success)
    assert "Stock for" in messages and "1" in messages


def test_the_inventory_caveat_switches_to_active_once_stock_is_loaded(isolated_db):
    from repositories.sqlite_repository import SQLiteRepository

    _, products = SQLiteRepository(db_path=isolated_db).load_data()
    product = next(iter(products))

    at = _boot()
    captions_before = " ".join(c.value for c in at.caption)
    assert "not computed" in captions_before

    at = _upload_stock(at, product)
    captions_after = " ".join(c.value for c in at.caption)
    assert "is computed from this session" in captions_after


def test_a_recomputed_recommendation_nets_off_the_uploaded_stock(isolated_db):
    """الاختبار الجوهري: الكمية بعد رفع المخزون = الكمية قبله ناقص المخزون.

    نفس الحساب الذي recommend_production ينفّذه منذ بنائه
    (_available_stock) — لكن run_batch كان يمرّ عليه None دائماً، فلا شيء
    كان يخصمه فعلياً في الواجهة قبل هذه الميزة.
    """
    from repositories.recommendation_repository import RecommendationRepository
    from repositories.sqlite_repository import SQLiteRepository

    _, products = SQLiteRepository(db_path=isolated_db).load_data()

    at = _boot()
    at = _recompute(at)

    repo = RecommendationRepository(db_path=isolated_db)
    baseline = {
        r.product_name: r.recommended_quantity
        for r in repo.highest_risk(limit=len(products))
    }
    # منتج له كمية موصى بها فعلية (لا "أنتج 0") ليكون الخصم قابلاً للقياس.
    product = next(name for name, qty in baseline.items() if qty > 10)

    at = _upload_stock(at, product)
    at = _recompute(at)

    updated = repo.latest_for_product(product)
    assert updated.recommended_quantity == pytest.approx(baseline[product] - 5.0)
