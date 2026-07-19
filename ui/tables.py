# ui/tables.py
import pandas as pd
import streamlit as st

from ui.i18n import format_months, t

# مفاتيح داخلية ثابتة — لا تُترجَم.
#
# كانت أسماء الأعمدة عربية *وتُستخدم مفاتيحَ* في آنٍ واحد
# (df['الكمية'].diff()). ترجمتها مباشرةً كانت ستكسر كل سطر يشير إليها.
# الفصل هنا: الحساب بمفاتيح ثابتة، والترجمة عند العرض وحده.
PERIOD = "_period"
QUANTITY = "_qty"
CHANGE = "_change"
CHANGE_PCT = "_change_pct"
CUMULATIVE = "_cumulative"


def render_details_table(selected_months, series, granularity="monthly"):
    """عرض جدول البيانات التفصيلية مع التغيرات (تاريخ فعلي فقط)"""
    df_details = pd.DataFrame({
        PERIOD: format_months(list(selected_months)),
        QUANTITY: series,
    })
    df_details[CHANGE] = df_details[QUANTITY].diff()
    df_details[CHANGE_PCT] = df_details[QUANTITY].pct_change() * 100
    df_details[CUMULATIVE] = df_details[QUANTITY].cumsum()

    for col in [QUANTITY, CHANGE, CUMULATIVE]:
        df_details[col] = df_details[col].apply(
            lambda x: f"{x:,.1f}" if pd.notnull(x) and x % 1 != 0
            else f"{x:,.0f}" if pd.notnull(x) else ""
        )
    df_details[CHANGE_PCT] = df_details[CHANGE_PCT].apply(
        lambda x: f"{x:.1f}%" if pd.notnull(x) else ""
    )

    st.dataframe(
        df_details.rename(columns={
            PERIOD: t(f"granularity.one.{granularity}"),
            QUANTITY: t("common.quantity"),
            CHANGE: t("table.change"),
            CHANGE_PCT: t("table.change_pct"),
            CUMULATIVE: t("table.cumulative"),
        }),
        use_container_width=True, height=400,
    )
