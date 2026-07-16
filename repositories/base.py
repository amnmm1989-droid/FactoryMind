# repositories/base.py
from abc import ABC, abstractmethod
from typing import Tuple, List, Dict, Any

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