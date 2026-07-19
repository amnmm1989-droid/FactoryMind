# ui/export.py
"""
تصدير تاريخ المنتج المعروض. لا ورقة تنبؤ: عرض المحلّل وصفي بحت الآن
(راجع ui/dashboard.py)، والتنبؤ يُصدَّر من صفحته الخاصة.
"""
from io import BytesIO, StringIO

import pandas as pd
import streamlit as st

from ui.i18n import t


def render_export_buttons(main_product, selected_months, series):
    """عرض أزرار تصدير البيانات"""
    st.subheader(t("old.export"))

    frame = pd.DataFrame({
        t("common.period"): selected_months,
        t("common.quantity"): series,
    })

    csv_buffer = StringIO()
    frame.to_csv(csv_buffer, index=False, encoding='utf-8-sig')

    col1, col2 = st.columns(2)
    col1.download_button(
        label=t("old.download_csv"),
        data=csv_buffer.getvalue(),
        file_name=f"{main_product.replace(' ', '_')}_data.csv",
        mime="text/csv",
        use_container_width=True,
    )

    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        frame.to_excel(writer, sheet_name=t("old.sheet_data")[:31], index=False)
    col2.download_button(
        label=t("old.download_excel"),
        data=excel_buffer.getvalue(),
        file_name=f"{main_product.replace(' ', '_')}_history.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
