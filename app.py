# app.py
import streamlit as st
from config import PAGE_TITLE, PAGE_ICON, LAYOUT, INITIAL_SIDEBAR_STATE
from utils.data_loader import get_repository
from ui.sidebar import render_sidebar
from ui.dashboard import render_dashboard

# ===================================================
#  إعدادات الصفحة
# ===================================================
st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout=LAYOUT,
    initial_sidebar_state=INITIAL_SIDEBAR_STATE
)

st.title("🔮 نظام تحليل وتنبؤ أوامر التصنيع – الإصدار الاحترافي")

# ===================================================
#  تهيئة session_state
# ===================================================
if 'show_seasonal' not in st.session_state:
    st.session_state.show_seasonal = True
if 'show_correlation' not in st.session_state:
    st.session_state.show_correlation = True
if 'show_distribution' not in st.session_state:
    st.session_state.show_distribution = True
if 'selected_products' not in st.session_state:
    st.session_state.selected_products = []
if 'show_trend' not in st.session_state:
    st.session_state.show_trend = True

# ===================================================
#  تحميل البيانات عبر Repository
# ===================================================
try:
    repo = get_repository()
    months, products = repo.load_data()
    product_names = repo.get_products()
except Exception as e:
    st.error(f"⚠️ تعذر تحميل البيانات: {str(e)}")
    st.stop()

# ===================================================
#  عرض الشريط الجانبي والحصول على الخيارات
# ===================================================
options = render_sidebar(months, product_names)

# ===================================================
#  عرض لوحة التحكم الرئيسية
# ===================================================
render_dashboard(months, products, options)