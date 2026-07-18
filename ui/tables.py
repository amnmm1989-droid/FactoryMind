# ui/tables.py
import numpy as np
import pandas as pd
import streamlit as st

from ui.i18n import format_months, t

# مفاتيح داخلية ثابتة — لا تُترجَم.
#
# كانت أسماء الأعمدة عربية *وتُستخدم مفاتيحَ* في آنٍ واحد
# (df['الكمية'].diff()). ترجمتها مباشرةً كانت ستكسر كل سطر يشير إليها.
# الفصل هنا: الحساب بمفاتيح ثابتة، والترجمة عند العرض وحده.
MONTH = "_month"
QUANTITY = "_qty"
CHANGE = "_change"
CHANGE_PCT = "_change_pct"
CUMULATIVE = "_cumulative"


def render_details_table(selected_months, series, forecast_months, forecast_vals,
                         granularity="monthly"):
    """عرض جدول البيانات التفصيلية مع التغيرات"""
    df_details = pd.DataFrame({
        MONTH: format_months(list(selected_months)),
        QUANTITY: series,
    })
    df_details[CHANGE] = df_details[QUANTITY].diff()
    df_details[CHANGE_PCT] = df_details[QUANTITY].pct_change() * 100
    df_details[CUMULATIVE] = df_details[QUANTITY].cumsum()

    if len(forecast_months) > 0:
        forecast_df = pd.DataFrame({
            MONTH: format_months(list(forecast_months)),
            QUANTITY: forecast_vals,
            CHANGE: np.nan,
            CHANGE_PCT: np.nan,
            CUMULATIVE: np.nan,
        })
        df_details = pd.concat([df_details, forecast_df], ignore_index=True)

    for col in [QUANTITY, CHANGE, CUMULATIVE]:
        if col in df_details.columns:
            df_details[col] = df_details[col].apply(
                lambda x: f"{x:,.1f}" if pd.notnull(x) and x % 1 != 0
                else f"{x:,.0f}" if pd.notnull(x) else ""
            )
    df_details[CHANGE_PCT] = df_details[CHANGE_PCT].apply(
        lambda x: f"{x:.1f}%" if pd.notnull(x) else ""
    )

    st.dataframe(
        df_details.rename(columns={
            MONTH: t(f"granularity.one.{granularity}"),
            QUANTITY: t("common.quantity"),
            CHANGE: t("table.change"),
            CHANGE_PCT: t("table.change_pct"),
            CUMULATIVE: t("table.cumulative"),
        }),
        use_container_width=True, height=400,
    )
