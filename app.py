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
from migrate import migrate
from repositories.base import resolve_db_path
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


@st.cache_resource(show_spinner=False)
def _ensure_database(db_path: str) -> None:
    """يبني القاعدة عند الإقلاع إن لم تكن مبنية.

    بدون هذا، الاستضافة مستحيلة: `data/app.db` مُتجاهَل في git عن حق،
    فالاستنساخ يصل بلا قاعدة. ومنصّة مثل Streamlit Cloud تشغّل
    `streamlit run app.py` وكفى — لا موضع فيها لأمر طرفية قبله. كانت
    النتيجة أن كل زائر يرى "شغّل: python migrate.py" على خادم لا يملكه.

    آمن في الوضعين: migrate() نفسه idempotent وذرّي، ولا يبني إلا البنية
    وبيانات العرض العامة. ملف المستخدم لا يمرّ من هنا إطلاقاً — يبقى في
    الذاكرة (ui/data_source.py).

    cache_resource لا تجميلاً: app.py يُعاد تنفيذه عند كل تفاعل، وقراءة
    القرص والتحقق من الانحراف عند كل ضغطة زر ثمن بلا مقابل. مرة لكل عملية.

    db_path وسيطٌ ولا يُقرأ من الوحدة مباشرةً — وهو مفتاح الـ cache. بلا
    وسيط تُخزَّن نتيجة أول استدعاء لكل قاعدة قادمة: صار الإقلاع الثاني
    يظنّ نفسه مُنجَزاً على قاعدة لم تُبنَ قط. كشفه اختبار الإقلاع البارد
    حين فشل جماعياً ونجح منفرداً.
    """
    migrate(db_path, verbose=False)


try:
    # resolve_db_path() لا DATABASE_PATH المستوردة: القيمة تُقرأ الآن، وهي
    # مفتاح الـ cache أعلاه — فلا يخلط إقلاعان قاعدتين.
    _ensure_database(resolve_db_path())
    render_upload_widget()
    months, products, is_user_data = active_dataset()
except MigrationError as exc:
    # يبقى المسار الصريح: الآن لا يعني "لم تُشغّل migrate.py" بل أنها
    # حاولت وفشلت (قرص للقراءة فقط، انحراف checksum، migration معطوب).
    # وهي حالات تستحق رسالة صريحة لا "no such table" غامضاً بعد حين.
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
