# ui/pages/advanced_analytics.py
"""
التحليل المتقدّم — الصفحة الأصلية، بلا تغيير في سلوكها.

تبقى كما وعدت خارطة الطريق: "الصفحة الحالية تبقى متاحة كـ Advanced
Analytics View للمحلل". هذا الملف غلاف رقيق حول ui/sidebar + ui/dashboard
القائمين — لم يُمسّ أيٌّ منهما.

⚠️ تحذير للمستخدم مقصود: هذه الصفحة تُشغّل ETS دائماً وتسمّيه "نموذج
التنبؤ". على هذا الكتالوج ترتيب ETS الثامن من تسعة. صفحة **التنبؤ**
تُشغّل كل النماذج وتختار بالأدلة. أُبقيت هذه لأن المحلل يعتمد على
تحليلاتها (الارتباط، التوزيع، الموسمية) التي لا توجد في الصفحات الجديدة.
"""
from __future__ import annotations

import streamlit as st

from ui.dashboard import render_dashboard
from ui.sidebar import render_sidebar


def render(months: list[str], products: dict[str, list[float]]) -> None:
    # العنوان كان في app.py قبل Phase 6؛ نُقل هنا كي تبقى الصفحة كما كانت
    st.title("🔮 نظام تحليل وتنبؤ أوامر التصنيع – الإصدار الاحترافي")
    st.info(
        "هذه الصفحة تُشغّل **ETS** دائماً — ترتيبه الثامن من تسعة على هذا "
        "الكتالوج. لاختيار النموذج بالأدلة استخدم صفحة **التنبؤ**. "
        "تبقى هنا لتحليلاتها الإحصائية (الارتباط، التوزيع، الموسمية).",
        icon="ℹ️",
    )
    options = render_sidebar(months, sorted(products))
    render_dashboard(months, products, options)
