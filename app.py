# app.py
"""
نقطة الدخول — قشرة تنقّل لا لوحة.

قبل Phase 6 كان هذا الملف يبني اللوحة الوحيدة مباشرةً. الآن يوزّع على
خمس صفحات ولا يحسب شيئاً بنفسه.

الترتيب مقصود: التنفيذية أولاً (ما الذي يحتاج انتباهي؟)، ثم التنبؤ
(المحرك الكامل)، ثم التخطيط، ثم ذكاء المنتج، والتحليل المتقدّم أخيراً —
الصفحة الأصلية، للمحلل لا لمدير الإنتاج.
"""
import streamlit as st

from config import INITIAL_SIDEBAR_STATE, LAYOUT, PAGE_ICON, PAGE_TITLE
from core.exceptions import MigrationError
from ui.data_source import active_dataset, render_upload_widget
from ui.i18n import render_language_switcher, t

st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout=LAYOUT,
    initial_sidebar_state=INITIAL_SIDEBAR_STATE,
)

# session_state للصفحة القديمة — ui/sidebar.py يقرأها كما كان
for key, default in [
    ("show_seasonal", True),
    ("show_correlation", True),
    ("show_distribution", True),
    ("show_trend", True),
    ("selected_products", []),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# المبدّل قبل كل شيء: زائر لا يقرأ العربية يجب أن يجد المخرج قبل أن
# يقرر أن الأداة ليست له.
render_language_switcher()

try:
    render_upload_widget()
    months, products, is_user_data = active_dataset()
except MigrationError as exc:
    # الـ schema مملوكة لـ migrations/ منذ Phase 2 — الفشل هنا صريح ومع
    # تعليمات، لا "no such table" غامض عند أول استعلام.
    st.error(f"⚠️ {exc.message}")
    st.code("python migrate.py", language="bash")
    st.stop()
except Exception as exc:  # noqa: BLE001
    st.error(t("app.load_failed", detail=exc))
    st.stop()


def _page(module_name: str):
    """كل صفحة تُستورَد كسولاً وتُنفَّذ بتوقيع render(months, products).

    الاستيراد الكسول مقصود: صفحة التنبؤ تجرّ statsmodels/prophet، ولا
    داعي لدفع ثمنها عند فتح التخطيط.
    """
    def run() -> None:
        import importlib

        importlib.import_module(f"ui.pages.{module_name}").render(months, products)

    return run


# url_path صريح لكل صفحة — إلزامي هنا: Streamlit يشتقّ المسار من اسم
# الدالة حين لا يُعطى، وكل ما يُرجعه _page() اسمه `run`، فتتصادم الصفحات
# الخمس على المسار نفسه وترفع StreamlitAPIException.
navigation = st.navigation([
    st.Page(_page("executive"), title=t("nav.executive"), icon="📊",
            url_path="executive", default=True),
    st.Page(_page("forecasting"), title=t("nav.forecasting"), icon="🔮",
            url_path="forecasting"),
    st.Page(_page("production_planning"), title=t("nav.planning"), icon="🏭",
            url_path="production-planning"),
    st.Page(_page("product_intelligence"), title=t("nav.intelligence"), icon="🧠",
            url_path="product-intelligence"),
    st.Page(_page("advanced_analytics"), title=t("nav.advanced"), icon="📈",
            url_path="advanced-analytics"),
])
navigation.run()
