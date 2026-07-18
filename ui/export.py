# ui/export.py
import streamlit as st

from ui.i18n import t
import pandas as pd
from io import BytesIO, StringIO

def render_export_buttons(main_product, selected_months, series, forecast_months, forecast_vals, lower_vals, upper_vals):
    """عرض أزرار تصدير البيانات"""
    st.subheader(t("old.export"))

    csv_buffer = StringIO()
    df_export = pd.DataFrame({
        'الشهر': selected_months,
        'الكمية': series
    })
    df_export.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
    csv_str = csv_buffer.getvalue()

    col_exp1, col_exp2, col_exp3 = st.columns(3)
    col_exp1.download_button(
        label=t("old.download_csv"),
        data=csv_str,
        file_name=f"{main_product.replace(' ', '_')}_data.csv",
        mime="text/csv",
        use_container_width=True
    )

    try:
        import openpyxl
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_export.to_excel(writer, sheet_name='البيانات', index=False)
            pd.DataFrame({
                'الشهر المتوقع': forecast_months,
                'القيمة المتوقعة': forecast_vals,
                'الحد الأدنى': lower_vals,
                'الحد الأعلى': upper_vals
            }).to_excel(writer, sheet_name='التنبؤ', index=False)
        excel_data = excel_buffer.getvalue()
        col_exp2.download_button(
            label=t("old.download_excel"),
            data=excel_data,
            file_name=f"{main_product.replace(' ', '_')}_forecast.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    except ImportError:
        col_exp2.info(
            "لتتمكن من تصدير Excel، قم بتثبيت openpyxl: `pip install openpyxl`",
            icon=":material/info:",
        )