"""
شاشة ربط الأعمدة اليدوي — مدفوعة عبر AppTest، لا اختبار وحدة على منطق معزول.

نفس مبدأ tests/test_cold_boot.py: يشغّل app.py الحقيقي، لا دالة تحته.
السبب هنا أدقّ من المعتاد: كل التسلسل (رفع → فشل التخمين → ظهور شاشة
الربط → اختيار الأعمدة → نجاح) يعبر session_state وwidget keys مربوطة
بـ file_id — وهذه لا تُختبَر بمعزل عن Streamlit فعلياً، بل بتشغيله.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")

UNRECOGNIZED_CSV = (
    "Ident,Zeitraum,Betrag\n"
    "PUMP-01,2024-01,10\nPUMP-01,2024-02,12\n"
    "PUMP-01,2024-03,9\nPUMP-01,2024-04,11\n"
).encode("utf-8")


@pytest.fixture(autouse=True)
def _isolate_streamlit_caches():
    """راجع تبرير مطابق في tests/test_cold_boot.py — نفس الحاجة هنا:
    _demo_dataset مُخزَّن بـ cache_data، ويجب ألا يُسرّب حالة بين الاختبارات."""
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


def _upload(at: AppTest, content: bytes, name: str = "export.csv") -> AppTest:
    at.sidebar.file_uploader[0].set_value([(name, content, "text/csv")])
    at.run()
    assert not at.exception
    return at


def test_an_unrecognized_file_shows_the_mapping_expander_not_a_dead_end():
    """السيناريو الذي وُجدت الشاشة لأجله: تخمين فاشل تماماً — لا يُرفَض
    الملف نهائياً، بل تُعرض أعمدته الفعلية."""
    at = _boot()
    at = _upload(at, UNRECOGNIZED_CSV)

    expander_labels = [e.label for e in at.sidebar.expander]
    assert any("Map columns" in label for label in expander_labels)


def test_the_dropdowns_offer_the_files_actual_columns():
    at = _boot()
    at = _upload(at, UNRECOGNIZED_CSV)

    selectboxes = at.sidebar.selectbox
    mapping_boxes = [
        sb for sb in selectboxes
        if set(sb.options) >= {"Ident", "Zeitraum", "Betrag"}
    ]
    assert len(mapping_boxes) == 3  # عمود المنتج، الشهر، الكمية


def test_choosing_the_three_columns_and_applying_loads_the_file():
    """المسار الكامل: رفع → فشل تلقائي → اختيار يدوي → نجاح."""
    at = _boot()
    at = _upload(at, UNRECOGNIZED_CSV)

    boxes = {sb.label: sb for sb in at.sidebar.selectbox}
    boxes["Product column"].select("Ident").run()
    boxes["Month column"].select("Zeitraum").run()
    boxes["Quantity column"].select("Betrag").run()

    apply_button = next(
        b for b in at.sidebar.button if b.label == "Use this mapping"
    )
    assert not apply_button.disabled  # الأعمدة الثلاثة مختلفة ومختارة كلها

    apply_button.click().run()

    assert not at.exception
    dataset = at.session_state["uploaded_dataset"]
    assert dataset.products == {"PUMP-01": [10.0, 12.0, 9.0, 11.0]}
    assert any(
        "Your file" in s.value for s in at.sidebar.success
    )


def test_the_apply_button_stays_disabled_until_all_three_are_chosen():
    """لا تسمح بربط ناقص — الثلاثة أو لا شيء."""
    at = _boot()
    at = _upload(at, UNRECOGNIZED_CSV)

    boxes = {sb.label: sb for sb in at.sidebar.selectbox}
    boxes["Product column"].select("Ident").run()
    # الشهر والكمية لم يُختارا بعد

    apply_button = next(
        b for b in at.sidebar.button if b.label == "Use this mapping"
    )
    assert apply_button.disabled


def test_picking_the_same_column_twice_disables_the_button():
    at = _boot()
    at = _upload(at, UNRECOGNIZED_CSV)

    boxes = {sb.label: sb for sb in at.sidebar.selectbox}
    boxes["Product column"].select("Ident").run()
    boxes["Month column"].select("Ident").run()  # نفس عمود المنتج
    boxes["Quantity column"].select("Betrag").run()

    apply_button = next(
        b for b in at.sidebar.button if b.label == "Use this mapping"
    )
    assert apply_button.disabled


def test_a_recognized_file_never_shows_the_mapping_screen():
    """انحدار عكسي: الملف الذي ينجح تخمينه لا يجب أن تظهر له الشاشة."""
    recognized = (
        "product,month,quantity\n"
        "A,Jan 2024,10\nA,Feb 2024,20\nA,Mar 2024,30\n"
    ).encode("utf-8")

    at = _boot()
    at = _upload(at, recognized, name="ok.csv")

    expander_labels = [e.label for e in at.sidebar.expander]
    assert not any("Map columns" in label for label in expander_labels)
    assert at.session_state["uploaded_dataset"].products == {
        "A": [10.0, 20.0, 30.0]
    }


def test_a_file_too_narrow_to_map_shows_no_mapping_screen():
    """أقل من ثلاثة أعمدة: لا فائدة من ربط لا يملك ما يكفي من أدوار."""
    too_narrow = "p,m\nX,Y\n".encode("utf-8")

    at = _boot()
    at = _upload(at, too_narrow, name="narrow.csv")

    expander_labels = [e.label for e in at.sidebar.expander]
    assert not any("Map columns" in label for label in expander_labels)
