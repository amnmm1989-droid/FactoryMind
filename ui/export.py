# ui/export.py
"""
تصدير تاريخ المنتج المعروض. لا ورقة تنبؤ: عرض المحلّل وصفي بحت الآن
(راجع ui/dashboard.py)، والتنبؤ يُصدَّر من صفحته الخاصة.
"""
from io import BytesIO, StringIO

import pandas as pd
import streamlit as st

from ui.i18n import format_months, t


def render_export_buttons(main_product, selected_months, series):
    """عرض أزرار تصدير البيانات.

    ⚠️ التسميات تمرّ بـ format_months كما تمرّ في الرسم والجدول. بدونها
    كان الملف المُصدَّر يحمل تسمية غير التي عُرضت على الشاشة: بالعربية،
    الشاشة "يناير 2023" والملف "January 2023" — واختلاف قِيس على الملف
    الشهري وحده (بقية الحبيبات تمرّ كما هي، فلم يظهر الفرق إلا بالعربية).

    من يُصدّر ليُرسل الملف يقارنه بما رآه؛ عمود فترة بلغة أخرى يبدو ملفاً
    لمنتج آخر.
    """
    st.subheader(t("old.export"))

    frame = pd.DataFrame({
        t("common.period"): format_months(list(selected_months)),
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


def audit_frame(provenance) -> pd.DataFrame:
    """سجلّ التدقيق كإطار جاهز لورقة Excel.

    القيم التي تبدأ بـ"audit." مفاتيح ترجمة لا نصوص — الخدمة تُرجع رمزاً
    والواجهة تترجمه، كما في Warning_. فيقرأ المصنع الإنجليزي ورقةً
    إنجليزية لا عربية.
    """
    return pd.DataFrame(
        [
            {
                t("audit.field"): t(key),
                t("audit.value"): t(value) if value.startswith("audit.") else value,
            }
            for key, value in provenance.rows()
        ]
    )


def write_audit_sheet(writer, provenance) -> None:
    """ورقة السجلّ في أي ملف مُصدَّر — نقطة واحدة كي لا يفترق ملفٌ عن آخر."""
    audit_frame(provenance).to_excel(
        writer, sheet_name=t("audit.sheet")[:31], index=False
    )
