# app.py
"""
نقطة الدخول — قشرة تنقّل لا لوحة.

قبل Phase 6 كان هذا الملف يبني اللوحة الوحيدة مباشرةً. الآن يوزّع على
سبع صفحات ولا يحسب شيئاً بنفسه.

الترتيب مقصود: التنفيذية أولاً (ما الذي يحتاج انتباهي؟)، ثم التنبؤ
(المحرك الكامل)، ثم التخطيط، ثم ذكاء المنتج، والتحليل المتقدّم — الصفحة
الأصلية، للمحلل لا لمدير الإنتاج — ثم ذكاء العميل: البُعد الثالث
(Roadmap بند 5)، لمدير المبيعات لا الإنتاج — وأخيراً خطة الشراء، لمدير
المشتريات: أفق تغطية يختاره هو، مُصدَّراً Excel مباشرة.
"""
import streamlit as st

from config import INITIAL_SIDEBAR_STATE, LAYOUT, PAGE_ICON
from core.exceptions import MigrationError
from migrate import migrate
from repositories.base import resolve_db_path
from ui.data_source import active_dataset, render_upload_widget
from ui.i18n import page_title, render_language_switcher, t

st.set_page_config(
    # لا PAGE_TITLE من config.py: كان نصاً عربياً مثبَّتاً يجعل تبويب
    # المتصفّح عربياً مهما كانت لغة الصفحة.
    page_title=page_title(),
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
    months, products, is_user_data = active_dataset()
except MigrationError as exc:
    # يبقى المسار الصريح: الآن لا يعني "لم تُشغّل migrate.py" بل أنها
    # حاولت وفشلت (قرص للقراءة فقط، انحراف checksum، migration معطوب).
    # وهي حالات تستحق رسالة صريحة لا "no such table" غامضاً بعد حين.
    st.error(exc.message, icon=":material/error:")
    st.code("python migrate.py", language="bash")
    st.stop()
except Exception as exc:  # noqa: BLE001
    st.error(t("app.load_failed", detail=exc), icon=":material/error:")
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
    st.Page(_page("executive"), title=t("nav.executive"), icon=":material/dashboard:",
            url_path="executive", default=True),
    st.Page(_page("forecasting"), title=t("nav.forecasting"), icon=":material/insights:",
            url_path="forecasting"),
    st.Page(_page("production_planning"), title=t("nav.planning"), icon=":material/factory:",
            url_path="production-planning"),
    st.Page(_page("product_intelligence"), title=t("nav.intelligence"), icon=":material/psychology:",
            url_path="product-intelligence"),
    st.Page(_page("advanced_analytics"), title=t("nav.advanced"), icon=":material/analytics:",
            url_path="advanced-analytics"),
    st.Page(_page("customer_intelligence"), title=t("nav.customers"), icon=":material/handshake:",
            url_path="customer-intelligence"),
    st.Page(_page("purchase_plan"), title=t("nav.purchase_plan"), icon=":material/shopping_cart:",
            url_path="purchase-plan"),
])
navigation.run()

# بعد الصفحة لا قبلها: ضوابط الصفحة (أفق، اختيار منتج، زر حساب) تُلمَس في
# كل زيارة؛ رفع الملف والمخزون يُلمَس مرة عند الإعداد. رفعه هنا يجعل ما
# يتكرر استخدامه أول ما يظهر، لا آخره خلف رسائل نجاح ورفع سابقتين.
render_upload_widget()
