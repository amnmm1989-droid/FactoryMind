"""
"بلا تاريخ مبيعات" + التوفيق الهرمي — مدفوعة عبر AppTest، لا اختبار
منطق معزول. نفس مبدأ tests/test_column_mapping_ui.py: يشغّل app.py
الحقيقي، والتفاعل (رفع، استعارة، رؤية الإجماليات) يعبر session_state
الحقيقي لا دالة تحت الاختبار.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")

# PumpB بلا مبيعات إطلاقاً — العطل الذي يسدّه القسم: منتج جديد ومنتج ميت
# يتطابقان في البيانات (أصفار كاملة)، وكان كلاهما يختفي بصمت.
CATALOGUE_WITH_A_DEAD_PRODUCT = (
    "product,category,month,quantity\n"
    "PumpA,Pumps,Jan 2024,10\nPumpA,Pumps,Feb 2024,12\n"
    "PumpA,Pumps,Mar 2024,9\nPumpA,Pumps,Apr 2024,11\n"
    "PumpB,Pumps,Jan 2024,0\nPumpB,Pumps,Feb 2024,0\n"
    "PumpB,Pumps,Mar 2024,0\nPumpB,Pumps,Apr 2024,0\n"
    "ValveA,Valves,Jan 2024,5\nValveA,Valves,Feb 2024,6\n"
    "ValveA,Valves,Mar 2024,4\nValveA,Valves,Apr 2024,7\n"
).encode("utf-8")


@pytest.fixture(autouse=True)
def _isolate_streamlit_caches():
    """راجع التبرير المطابق في test_cold_boot.py وtest_column_mapping_ui.py."""
    import streamlit as st

    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


def _boot() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def _upload(at: AppTest, content: bytes, name: str = "catalogue.csv") -> AppTest:
    at.sidebar.file_uploader[0].set_value([(name, content, "text/csv")])
    at.run()
    assert not at.exception
    return at


def test_a_product_with_zero_sales_is_visible_not_silently_dropped():
    """العطل نفسه: PumpB بلا تاريخ — يجب أن يظهر، لا أن يختفي."""
    at = _boot()
    at = _upload(at, CATALOGUE_WITH_A_DEAD_PRODUCT)

    expander_labels = [e.label for e in at.expander]
    assert any("No sales history" in label for label in expander_labels)


def test_the_dead_product_is_not_in_the_main_recommendations():
    """لا توصية بلا استعارة — PumpB لم يُحسب له شيء بعد."""
    at = _boot()
    at = _upload(at, CATALOGUE_WITH_A_DEAD_PRODUCT)

    names = {r.product_name for r in at.session_state["session_recommendations"]}
    assert "PumpB" not in names
    assert "PumpA" in names
    assert "ValveA" in names


def test_category_totals_appear_and_are_exact():
    """Bottom-Up: إجمالي Pumps = توصية PumpA بالضبط (PumpB بلا توصية بعد)."""
    at = _boot()
    at = _upload(at, CATALOGUE_WITH_A_DEAD_PRODUCT)

    expander_labels = [e.label for e in at.expander]
    assert any("By category" in label for label in expander_labels)

    recs = {r.product_name: r for r in at.session_state["session_recommendations"]}
    category_frame = next(
        df.value for df in at.dataframe
        if "Category" in list(df.value.columns)
    )
    pumps_row = category_frame[category_frame["Category"] == "Pumps"].iloc[0]
    assert pumps_row["Products"] == 1  # PumpA وحده حتى الآن
    # المقارنة نصّية (تنسيق _format_quantity) لا رقمية: العمود مُهيَّأ للعرض
    from ui.pages.executive import _format_quantity
    assert pumps_row["Recommended qty"] == _format_quantity(
        recs["PumpA"].recommended_quantity
    )


def test_borrowing_moves_the_product_out_of_no_history_and_into_recommendations():
    """المسار الكامل: رفع → PumpB بلا تاريخ → استعارة من PumpA → يظهر موصى به."""
    at = _boot()
    at = _upload(at, CATALOGUE_WITH_A_DEAD_PRODUCT)

    target_box = next(
        sb for sb in at.selectbox if "PumpB" in sb.options and "PumpA" not in sb.options
    )
    source_box = next(
        sb for sb in at.selectbox if "PumpA" in sb.options and "PumpB" not in sb.options
    )
    target_box.select("PumpB").run()
    source_box.select("PumpA").run()

    borrow_button = next(b for b in at.button if b.label == "Borrow this estimate")
    borrow_button.click().run()

    assert not at.exception
    recs = {r.product_name: r for r in at.session_state["session_recommendations"]}
    assert "PumpB" in recs
    assert recs["PumpB"].borrowed_from == "PumpA"

    # واختفى من قسم "بلا تاريخ" — لم يعد من no_history بعد الاستعارة
    expander_labels = [e.label for e in at.expander]
    assert not any("No sales history" in label for label in expander_labels)


def test_borrowed_product_is_marked_in_the_recommendations_table():
    """🔗 يلتصق بالاسم أينما ظهر — لا رقم يبدو محسوباً من تاريخ لا وجود له."""
    at = _boot()
    at = _upload(at, CATALOGUE_WITH_A_DEAD_PRODUCT)

    target_box = next(
        sb for sb in at.selectbox if "PumpB" in sb.options and "PumpA" not in sb.options
    )
    source_box = next(
        sb for sb in at.selectbox if "PumpA" in sb.options and "PumpB" not in sb.options
    )
    target_box.select("PumpB").run()
    source_box.select("PumpA").run()
    next(b for b in at.button if b.label == "Borrow this estimate").click().run()

    main_frame = next(
        df.value for df in at.dataframe if "Product" in list(df.value.columns)
    )
    marked = main_frame[main_frame["Product"].str.contains("PumpB", na=False)]
    assert len(marked) == 1
    assert marked.iloc[0]["Product"].startswith("🔗")


def test_category_total_stays_exact_after_borrowing():
    """التحقّق الحاسم: بعد الاستعارة، إجمالي Pumps = مجموع PumpA + PumpB
    بالضبط — لا تقريباً. هذا هو معيار قبول Bottom-Up حرفياً."""
    at = _boot()
    at = _upload(at, CATALOGUE_WITH_A_DEAD_PRODUCT)

    target_box = next(
        sb for sb in at.selectbox if "PumpB" in sb.options and "PumpA" not in sb.options
    )
    source_box = next(
        sb for sb in at.selectbox if "PumpA" in sb.options and "PumpB" not in sb.options
    )
    target_box.select("PumpB").run()
    source_box.select("PumpA").run()
    next(b for b in at.button if b.label == "Borrow this estimate").click().run()

    recs = {r.product_name: r for r in at.session_state["session_recommendations"]}
    expected_total = recs["PumpA"].recommended_quantity + recs["PumpB"].recommended_quantity

    from services.reconciliation import category_totals
    categories = {"PumpA": "Pumps", "PumpB": "Pumps", "ValveA": "Valves"}
    totals = {row.category: row.total_quantity for row in category_totals(categories, recs.values())}
    assert totals["Pumps"] == pytest.approx(expected_total)


def test_a_catalogue_with_no_dead_products_shows_no_history_section():
    """انحدار عكسي: كتالوج كامل التاريخ لا يظهر له قسم "بلا تاريخ" إطلاقاً."""
    healthy = (
        "product,category,month,quantity\n"
        "PumpA,Pumps,Jan 2024,10\nPumpA,Pumps,Feb 2024,12\nPumpA,Pumps,Mar 2024,9\n"
    ).encode("utf-8")

    at = _boot()
    at = _upload(at, healthy, name="healthy.csv")

    expander_labels = [e.label for e in at.expander]
    assert not any("No sales history" in label for label in expander_labels)


def test_a_catalogue_with_no_categories_shows_no_category_section():
    """انحدار عكسي: ملف بلا عمود فئة لا يظهر له قسم "حسب الفئة" إطلاقاً."""
    no_categories = (
        "product,month,quantity\n"
        "PumpA,Jan 2024,10\nPumpA,Feb 2024,12\nPumpA,Mar 2024,9\n"
    ).encode("utf-8")

    at = _boot()
    at = _upload(at, no_categories, name="nocat.csv")

    expander_labels = [e.label for e in at.expander]
    assert not any("By category" in label for label in expander_labels)
