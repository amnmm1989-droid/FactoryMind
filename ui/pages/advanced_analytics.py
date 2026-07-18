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
from ui.i18n import t
from ui.sidebar import render_sidebar


def render(months: list[str], products: dict[str, list[float]]) -> None:
    # العنوان كان في app.py قبل Phase 6؛ نُقل هنا كي تبقى الصفحة كما كانت
    st.title(t("adv.title"))
    st.info(t("adv.notice"), icon=":material/info:")
    options = render_sidebar(months, sorted(products))
    render_dashboard(months, products, options)
