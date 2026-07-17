# repositories/base.py
from abc import ABC, abstractmethod
from typing import Tuple, List, Dict, Any, Optional

import config


def resolve_db_path(db_path: Optional[str] = None) -> str:
    """مسار القاعدة — يُقرأ عند النداء لا عند الاستيراد.

    القراءة عبر `config.DATABASE_PATH` (سمة الوحدة) لا عبر
    `from config import DATABASE_PATH` (نسخة تُجمَّد في فضاء الوحدة عند
    استيرادها). الفرق ليس أسلوبياً:

    كانت المستودعات تكتب `def __init__(self, db_path=DATABASE_PATH)`، وقيمة
    الوسيط الافتراضية في بايثون تُقيَّم مرة واحدة عند تعريف الدالة وتلتصق
    بها للأبد. فمهما أُعيد توجيه القاعدة لاحقاً، تبقى كل نسخة تكتب في
    data/app.db الحقيقية.

    والثمن لم يكن نظرياً: مسار لا يُعاد توجيهه لا يُختبر، فلم يُختبر
    الإقلاع البارد قط، فوصل إلى الإنتاج معطّلاً — كل زائر يُطالَب بتشغيل
    `python migrate.py` على خادم لا طرفية له. أُصلح العطل في 0af823b،
    وهذا يُزيل السبب الذي أخفاه.

    None تعني "الافتراضي الحالي"، لا "لا مسار".
    """
    return db_path if db_path is not None else config.DATABASE_PATH


class DataRepository(ABC):
    """واجهة مجردة لطبقة الوصول إلى البيانات"""
    
    @abstractmethod
    def load_data(self) -> Tuple[List[str], Dict[str, List[float]]]:
        """
        تحميل جميع البيانات
        Returns:
            Tuple[List[str], Dict[str, List[float]]]: (months, products)
        """
        pass
    
    @abstractmethod
    def get_products(self) -> List[str]:
        """الحصول على قائمة بأسماء المنتجات"""
        pass
    
    @abstractmethod
    def get_months(self) -> List[str]:
        """الحصول على قائمة الأشهر"""
        pass
    
    @abstractmethod
    def get_product_data(self, product_name: str) -> List[float]:
        """الحصول على بيانات منتج محدد"""
        pass
    
    @abstractmethod
    def save_data(self, months: List[str], products: Dict[str, List[float]]) -> None:
        """حفظ البيانات (للإصدارات القادمة)"""
        pass
    
    @abstractmethod
    def get_metadata(self) -> Dict[str, Any]:
        """الحصول على معلومات وصفية عن البيانات (عدد المنتجات، عدد الأشهر، إلخ)"""
        pass