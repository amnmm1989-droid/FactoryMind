# tests/test_purchase_plan_ui.py
"""
صفحة خطة الشراء (ui/pages/purchase_plan.py) — مدفوعة عبر AppTest، نفس
تقنية tests/test_calibration_ui.py: صفحة مستقلة لا تعبر st.navigation في
app.py، فتُشغَّل عبر AppTest.from_function مباشرة.

لا قاعدة بيانات هنا خلافاً لصفحة المعايرة: خطة الشراء لا تُحفَظ، فلا حاجة
لعزل db_path.
"""
from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _run_page() -> AppTest:
    def script() -> None:
        from ui.pages.purchase_plan import render

        months = [f"m{i}" for i in range(24)]
        products = {
            "منتج نشط": [100.0 + i * 2 for i in range(24)],
            "منتج متوقّف": [80.0] * 6 + [0.0] * 18,
        }
        render(months, products)

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def test_initial_render_shows_the_empty_state_before_computing():
    at = _run_page()

    infos = " ".join(i.value for i in at.info)
    assert "Compute purchase plan" in infos or "احسب خطة الشراء" in infos
    assert len(at.dataframe) == 0


def test_clicking_compute_produces_a_purchase_table_and_download_button():
    at = _run_page()

    at.button[0].click().run()

    assert not at.exception
    assert len(at.dataframe) >= 1
    assert len(at.download_button) == 1


def test_dormant_product_is_excluded_from_the_main_table_but_not_hidden():
    at = _run_page()
    at.button[0].click().run()

    main_table = at.dataframe[0].value
    assert "منتج متوقّف" not in main_table.iloc[:, 0].tolist()

    expander_labels = " ".join(e.label for e in at.expander)
    assert "excluded" in expander_labels.lower() or "مستبعد" in expander_labels


def test_changing_horizon_changes_the_computed_result():
    at = _run_page()
    at.number_input[0].set_value(1).run()
    at.button[0].click().run()
    short_horizon_qty = at.dataframe[0].value.iloc[0][
        [c for c in at.dataframe[0].value.columns if "qty" in c.lower() or "recommended" in c.lower()][0]
    ]

    at.number_input[0].set_value(12).run()
    at.button[0].click().run()
    long_horizon_qty = at.dataframe[0].value.iloc[0][
        [c for c in at.dataframe[0].value.columns if "qty" in c.lower() or "recommended" in c.lower()][0]
    ]

    assert long_horizon_qty >= short_horizon_qty
