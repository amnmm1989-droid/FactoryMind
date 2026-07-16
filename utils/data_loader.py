# utils/data_loader.py
import streamlit as st
from repositories.factory import RepositoryFactory

@st.cache_resource
def get_repository():
    """إرجاع نسخة من DataRepository حسب الإعدادات في config.py"""
    return RepositoryFactory.get_repository()

@st.cache_data
def load_default_data():
    """
    تحميل البيانات من خلال Repository (المصدر محدد في config.py)
    إرجاع: (months, products)
    """
    repo = get_repository()
    return repo.load_data()