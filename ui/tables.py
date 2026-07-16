# ui/tables.py
import streamlit as st
import pandas as pd
import numpy as np

def render_details_table(selected_months, series, forecast_months, forecast_vals):
    """عرض جدول البيانات التفصيلية مع التغيرات"""
    df_details = pd.DataFrame({
        'الشهر': selected_months,
        'الكمية': series
    })
    df_details['التغير عن السابق'] = df_details['الكمية'].diff()
    df_details['نسبة التغير'] = df_details['الكمية'].pct_change() * 100
    df_details['التغير التراكمي'] = df_details['الكمية'].cumsum()

    if len(forecast_months) > 0:
        forecast_df = pd.DataFrame({
            'الشهر': forecast_months,
            'الكمية': forecast_vals,
            'التغير عن السابق': np.nan,
            'نسبة التغير': np.nan,
            'التغير التراكمي': np.nan
        })
        df_details = pd.concat([df_details, forecast_df], ignore_index=True)

    for col in ['الكمية', 'التغير عن السابق', 'التغير التراكمي']:
        if col in df_details.columns:
            df_details[col] = df_details[col].apply(lambda x: f"{x:,.1f}" if pd.notnull(x) and x % 1 != 0 else f"{x:,.0f}" if pd.notnull(x) else "")
    df_details['نسبة التغير'] = df_details['نسبة التغير'].apply(lambda x: f"{x:.1f}%" if pd.notnull(x) else "")

    st.dataframe(df_details, use_container_width=True, height=400)