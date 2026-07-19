# ui/pages/advanced_analytics.py
"""
عرض المحلّل — استكشاف التاريخ الفعلي وتصديره. **لا تنبؤ هنا.**

غلاف رقيق حول ui/sidebar + ui/dashboard.

قُلِّصت هذه الصفحة عمداً قبل طرح الأداة على مصانع حقيقية. كان مبرّرها
السابق "تحليلاتها الإحصائية (الارتباط، التوزيع، الموسمية)" — وهي بالضبط
ما ثبت أنه بلا فائدة أو مضلّل على كتالوج متقطّع، فأُزيل. راجع
ui/dashboard.py للأسباب المقيسة لكل قسم مُزال.

ما بقي هو ما لا توجد له بدائل في الصفحات الأربع الأخرى: مقارنة عدة منتجات
على محور واحد، كشف القيم الشاذة، إحصاءات وصفية، وجدول خام قابل للتصدير.
"""
from __future__ import annotations

import streamlit as st

from ui.data_source import active_granularity, products_by_volume
from ui.dashboard import render_dashboard
from ui.i18n import t
from ui.sidebar import render_sidebar


def render(months: list[str], products: dict[str, list[float]]) -> None:
    # العنوان كان في app.py قبل Phase 6؛ نُقل هنا كي تبقى الصفحة كما كانت
    st.title(t("adv.title"))
    st.info(t("adv.notice"), icon=":material/info:")
    granularity = active_granularity()
    # بالحجم لا أبجدياً: الشريط يختار `product_names[0]` افتراضاً، وكان
    # ذلك يعني أن عرض المحلّل يفتح على منتج بـ0.03% من الإنتاج.
    options = render_sidebar(months, products_by_volume(products), granularity)
    render_dashboard(months, products, options, granularity)
