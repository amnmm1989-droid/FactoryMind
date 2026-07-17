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
from utils.data_loader import get_repository

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


@st.cache_data(show_spinner="تحميل البيانات...")
def _load_data():
    return get_repository().load_data()


try:
    months, products = _load_data()
except MigrationError as exc:
    # الـ schema مملوكة لـ migrations/ منذ Phase 2 — الفشل هنا صريح ومع
    # تعليمات، لا "no such table" غامض عند أول استعلام.
    st.error(f"⚠️ {exc.message}")
    st.code("python migrate.py", language="bash")
    st.stop()
except Exception as exc:  # noqa: BLE001
    st.error(f"⚠️ تعذّر تحميل البيانات: {exc}")
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
    st.Page(_page("executive"), title="النظرة التنفيذية", icon="📊",
            url_path="executive", default=True),
    st.Page(_page("forecasting"), title="التنبؤ", icon="🔮",
            url_path="forecasting"),
    st.Page(_page("production_planning"), title="تخطيط الإنتاج", icon="🏭",
            url_path="production-planning"),
    st.Page(_page("product_intelligence"), title="ذكاء المنتج", icon="🧠",
            url_path="product-intelligence"),
    st.Page(_page("advanced_analytics"), title="التحليل المتقدّم", icon="📈",
            url_path="advanced-analytics"),
])
navigation.run()
