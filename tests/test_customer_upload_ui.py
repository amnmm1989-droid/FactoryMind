# tests/test_customer_upload_ui.py
"""
صفحة ذكاء العميل (Roadmap بند 5) — مدفوعة عبر AppTest.

نفس تقنية tests/test_adherence_dashboard_ui.py: صفحة مستقلة لا تعبر
st.navigation في app.py (AppTest.switch_page يحتاج ملف صفحة حقيقياً)،
فتُشغَّل عبر AppTest.from_function مباشرة.

⚠️ عزل القاعدة إلزامي رغم أن الصفحة لا تكتب في SQL إطلاقاً: render()
يحتاج توقيع (months, products) من الكتالوج المحلي — نفس عقد كل الصفحات.
"""
from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

CUSTOMER_CSV = (
    "Product,Customer,Month,Quantity\n"
    "Pump,ACME,Jan 2024,100\n"
    "Pump,Delta,Jan 2024,10\n"
    "Pump,Echo,Jan 2024,5\n"
    "Pump,ACME,Feb 2024,100\n"
    "Pump,Delta,Feb 2024,10\n"
    "Pump,Echo,Feb 2024,5\n"
    "Pump,ACME,Mar 2024,20\n"
    "Pump,Delta,Mar 2024,10\n"
    "Pump,Echo,Mar 2024,5\n"
    "Pump,ACME,Apr 2024,20\n"
    "Pump,Delta,Apr 2024,20\n"
    "Pump,Echo,Apr 2024,5\n"
).encode("utf-8")

UNRECOGNISED_CSV = (
    "Material,Sold-To,Zeitraum,Betrag\n"
    "PUMP-01,ACME,2024-01,10\nPUMP-01,ACME,2024-02,12\n"
).encode("utf-8")


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
        from ui.pages.customer_intelligence import render

        months, products = SQLiteRepository().load_data()
        render(months, products)

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def _upload(at: AppTest, content: bytes, name: str = "customers.csv") -> AppTest:
    at.sidebar.file_uploader[0].set_value([(name, content, "text/csv")])
    at.run()
    assert not at.exception
    return at


def test_no_file_shows_the_upload_prompt_not_a_crash(isolated_db):
    at = _run_page()

    assert any("Upload a sales-by-customer file" in i.value for i in at.info)


def test_uploading_a_recognised_file_shows_all_three_analyses(isolated_db):
    at = _run_page()
    at = _upload(at, CUSTOMER_CSV)

    subheaders = " ".join(h.value for h in at.subheader)
    assert "Customer concentration" in subheaders
    assert "Bleeding customers" in subheaders

    expanders = [e.label for e in at.expander]
    assert any("Growth by customer" in label for label in expanders)


def test_concentration_summary_reports_the_correct_top_customer_share(isolated_db):
    """ACME=240، Delta=50، Echo=20 عبر أربعة أشهر -> أعلى عميلين 290/310 = 94%."""
    at = _run_page()
    at = _upload(at, CUSTOMER_CSV)

    captions = " ".join(c.value for c in at.caption)
    assert "94%" in captions


def test_bleeding_customer_is_listed_with_its_decline(isolated_db):
    """ACME: 100 -> 20 (متوسط النصف الأول مقابل الثاني) = -80%، تحت العتبة."""
    at = _run_page()
    at = _upload(at, CUSTOMER_CSV)

    dataframe_values = [str(df.value) for df in at.dataframe]
    assert any("ACME" in value and "-80" in value for value in dataframe_values)


def test_an_unrecognised_file_offers_manual_column_mapping(isolated_db):
    at = _run_page()
    at = _upload(at, UNRECOGNISED_CSV, name="sap_export.csv")

    expander_labels = [e.label for e in at.expander]
    assert any("Map columns" in label for label in expander_labels)


def test_mapping_the_four_columns_and_applying_loads_the_file(isolated_db):
    at = _run_page()
    at = _upload(at, UNRECOGNISED_CSV, name="sap_export.csv")

    boxes = {sb.label: sb for sb in at.sidebar.selectbox}
    boxes["Product column"].select("Material").run()
    boxes["Customer column"].select("Sold-To").run()
    boxes["Month column"].select("Zeitraum").run()
    boxes["Quantity column"].select("Betrag").run()

    apply_button = next(b for b in at.button if b.label == "Use this mapping")
    assert not apply_button.disabled
    apply_button.click().run()

    assert not at.exception
    successes = " ".join(s.value for s in at.sidebar.success)
    assert "1" in successes
