# ui/charts.py
"""
رسوم عرض المحلّل — تاريخية بحتة.

أُزيلت رسوم الموسمية والارتباط والتوزيع مع تقليص الصفحة: راجع
ui/dashboard.py للأسباب المقيسة (موسمية ليست موسمية، ارتباطات زائفة على
بيانات متقطّعة، وتوزيع كتلته أصفار).
"""
import pandas as pd
import plotly.express as px

from ui.i18n import format_months, t

# أسماء الأعمدة تُترجَم عند البناء: هذه DataFrames تُنشأ وتُستهلَك داخل
# الدالة نفسها، فلا حاجة لمفاتيح ثابتة. ما يحتاجها هو ما يعبر حدود
# الطبقات (ui/tables.py).


def create_main_chart(selected_months, series, outliers, main_product,
                      granularity="monthly"):
    """إنشاء الرسم البياني الرئيسي (التاريخ الفعلي + إبراز الشواذّ)"""
    period = t(f"granularity.one.{granularity}")
    quantity = t("common.quantity")
    display_months = format_months(list(selected_months))

    frame = pd.DataFrame({period: display_months, quantity: series})
    fig = px.line(frame, x=period, y=quantity,
                  title=t("chart.history_of", product=main_product))

    if outliers:
        fig.add_scatter(
            x=[display_months[i] for i in outliers], y=[series[i] for i in outliers],
            mode='markers', marker=dict(color='red', size=10, symbol='x'),
            name=t("chart.outliers"),
        )

    fig.update_layout(height=450, margin=dict(l=0, r=0, t=40, b=0))
    return fig


def create_comparison_chart(selected_months, all_products_data, granularity="monthly"):
    """إنشاء رسم بياني لمقارنة المنتجات"""
    period = t(f"granularity.one.{granularity}")
    quantity, product = t("common.quantity"), t("common.product")
    display_months = format_months(list(selected_months))

    df_compare = pd.concat([
        pd.DataFrame({period: display_months, quantity: data, product: name})
        for name, data in all_products_data.items()
    ])

    fig = px.line(df_compare, x=period, y=quantity, color=product,
                  title=t("chart.performance_comparison"))
    fig.update_layout(height=400)
    return fig
