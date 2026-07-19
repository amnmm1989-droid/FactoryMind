# ui/dashboard.py
"""
عرض المحلّل — استكشاف التاريخ وتصديره، لا تنبؤ.

## ما أُزيل ولماذا (قرار مقيس، لا تنظيف تجميلي)

قُلِّصت هذه الصفحة عمداً قبل طرحها على مصانع حقيقية. أُزيل منها:

- **"التحليل الموسمي"**: كان يقسّم المدى إلى أربعة مقاطع متساوية ويأخذ
  متوسطها — وهذه ليست موسمية أصلاً (لا علاقة لها بموضع الفترة في الدورة)،
  فلا يخبر بشيء عند أي حبيبة.
- **مصفوفة الارتباط بين المنتجات**: على سلاسل 80–95% أصفار (هذا الكتالوج)
  الارتباطات زائفة غالباً — وخطرها أن يُبنى عليها قرار.
- **رسوم التوزيع**: توزيع سلسلة متقطّعة = كتلة أصفار + نتوء. منحنى الكثافة
  عليها بلا معنى.
- **تحليل الاتجاه** (الميل/R²/قيمة p): انحدار خطي على سلسلة متقطّعة كتلية
  يعطي أرقاماً تبدو علمية وهي هشّة — دقّة كاذبة.
- **التنبؤ (ETS/SARIMA)**: راجع services/product_analysis_service.py —
  مسار تنبؤ ثانٍ برقم مختلف عن صفحة التنبؤ، ونموذج ترتيبه 8/9.

ما بقي هو ما لا يوجد في الصفحات الأخرى فعلاً: مقارنة عدة منتجات، كشف
الشواذّ، إحصاءات وصفية، وجدول خام قابل للتصدير.
"""
import streamlit as st

from core.exceptions import InsufficientDataError
from core.logging_config import get_logger
from services.product_analysis_service import analyze_product
from ui.charts import create_comparison_chart, create_main_chart
from ui.export import render_export_buttons
from ui.i18n import format_month, format_months, t
from ui.tables import render_details_table

logger = get_logger(__name__)


# أقصى ما يُسرَد داخل سطر التحذير نفسه. الباقي في قائمة قابلة للطيّ.
#
# ⚠️ الحدّ ليس تجميلياً: على الملف اليومي في هذا الكتالوج تُكتشف **74**
# نقطة شاذّة، وسردها كلّها في سطر واحد يُنتج جداراً نصّياً يدفع الرسم
# البياني — وهو موضع الفائدة — خارج الشاشة. الرقم المهمّ ("كم شاذّة؟")
# يبقى في التحذير دائماً؛ التواريخ تفصيلٌ يُطلَب عند الحاجة.
MAX_OUTLIERS_INLINE = 8


def _render_outlier_notice(indices, selected_months, many) -> None:
    labels = format_months([selected_months[i] for i in indices])
    st.warning(
        t("old.outliers_found", count=len(labels), many=many,
          months="، ".join(labels[:MAX_OUTLIERS_INLINE])
                 + ("…" if len(labels) > MAX_OUTLIERS_INLINE else "")),
        icon=":material/warning:",
    )
    if len(labels) > MAX_OUTLIERS_INLINE:
        with st.expander(t("old.outliers_all", count=len(labels))):
            st.write("، ".join(labels))


def render_dashboard(months, products, options, granularity="monthly"):
    """
    عرض لوحة المحلّل الكاملة.
    options: dict يحتوي على الخيارات المختارة من الشريط الجانبي
    granularity: حبيبة الملف الفعلية — تُسمّى بها الوحدات المعروضة.
    """
    many = t(f"granularity.many.{granularity}")
    unit = t(f"granularity.unit.{granularity}")

    selected_products = options['selected_products']
    from_idx = options['from_idx']
    to_idx = options['to_idx']
    show_outliers = options['show_outliers']

    main_product = selected_products[0]
    data_main = products[main_product]
    selected_data_main = data_main[from_idx:to_idx+1]
    selected_months = months[from_idx:to_idx+1]

    all_products_data = {}
    for p in selected_products:
        all_products_data[p] = products[p][from_idx:to_idx+1]

    # ========== الوصف عبر Service Layer ==========
    try:
        analysis = analyze_product(
            product_name=main_product,
            selected_months=selected_months,
            series=selected_data_main,
            include_outliers=show_outliers,
        )
    except InsufficientDataError as e:
        logger.warning("Dashboard render aborted: %s", e)
        st.error(e.message, icon=":material/error:")
        st.stop()

    # ========== الإحصائيات الأساسية ==========
    stats = analysis.stats
    st.subheader(t("old.product_analysis", product=main_product))

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric(t("old.total"), f"{stats.total:,.0f}")
    col2.metric(t("old.average"), f"{stats.avg:,.1f}")
    col3.metric(t("old.max"), f"{stats.max:,.0f}")
    col4.metric(t("old.min_nonzero"), f"{stats.min:,.0f}")
    col5.metric(t("old.std"), f"{stats.std:,.1f}")
    col6.metric(t("old.median"), f"{stats.median:,.0f}")

    col7, col8, col9 = st.columns(3)
    col7.metric(t("old.nonzero_months", many=many).capitalize(), f"{stats.non_zero_count}")
    col8.metric(t("old.cv"), f"{stats.cv:.2%}")
    col9.metric(t("old.last_value"), f"{stats.last_val:,.0f}")

    # ========== كشف النقاط الشاذة ==========
    outlier_indices = []
    if show_outliers and analysis.outliers:
        outlier_indices = analysis.outliers.outlier_indices
        if outlier_indices:
            _render_outlier_notice(outlier_indices, selected_months, many)
        else:
            st.success(t("old.no_outliers"), icon=":material/check_circle:")

    # ========== الرسم البياني الرئيسي ==========
    st.subheader(t("old.main_chart"))
    fig = create_main_chart(
        selected_months, selected_data_main, outlier_indices, main_product,
        granularity,
    )
    st.plotly_chart(fig, use_container_width=True)

    # ========== مقارنة المنتجات ==========
    if len(selected_products) > 1:
        st.subheader(t("old.comparison_selected"))
        fig_compare = create_comparison_chart(selected_months, all_products_data, granularity)
        st.plotly_chart(fig_compare, use_container_width=True)

    # ========== جدول البيانات التفصيلية ==========
    st.subheader(t("old.details_table"))
    render_details_table(selected_months, selected_data_main, granularity)

    # ========== تصدير البيانات ==========
    render_export_buttons(main_product, selected_months, selected_data_main)

    # ========== تذييل ==========
    st.markdown("---")
    st.caption(t("old.footer"))
    st.caption(t("old.analysed_range",
                 start=format_month(selected_months[0]),
                 end=format_month(selected_months[-1]),
                 count=len(selected_months), unit=unit))
