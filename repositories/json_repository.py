# repositories/json_repository.py
import json
from typing import Tuple, List, Dict, Any
from repositories.base import DataRepository
from config import DATA_FILE

class JsonRepository(DataRepository):
    """تطبيق DataRepository باستخدام ملف JSON"""
    
    def __init__(self, file_path: str = DATA_FILE):
        self.file_path = file_path
        self._months = []
        self._products = {}
        self._load_from_file()
    
    def _load_from_file(self) -> None:
        """تحميل البيانات من ملف JSON وتخزينها داخلياً"""
        with open(self.file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self._months = data['months']
        self._products = data['products']
    
    def load_data(self) -> Tuple[List[str], Dict[str, List[float]]]:
        """إرجاع البيانات المحملة"""
        return self._months, self._products
    
    def get_products(self) -> List[str]:
        """إرجاع قائمة المنتجات مرتبة أبجدياً"""
        return sorted(self._products.keys())
    
    def get_months(self) -> List[str]:
        """إرجاع قائمة الأشهر"""
        return self._months.copy()
    
    def get_product_data(self, product_name: str) -> List[float]:
        """إرجاع بيانات منتج محدد"""
        return self._products.get(product_name, [])
    
    def save_data(self, months: List[str], products: Dict[str, List[float]]) -> None:
        """حفظ البيانات إلى ملف JSON (للإصدارات القادمة)"""
        data = {'months': months, 'products': products}
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # تحديث البيانات المخزنة داخلياً
        self._months = months
        self._products = products
    
    def get_metadata(self) -> Dict[str, Any]:
        """الحصول على معلومات وصفية عن البيانات"""
        total_products = len(self._products)
        total_months = len(self._months)
        # حساب عدد المنتجات التي تحتوي على بيانات (جميع القيم صفر)
        zero_products = sum(
            1 for data in self._products.values() 
            if all(v == 0 for v in data)
        )
        return {
            'total_products': total_products,
            'total_months': total_months,
            'zero_products': zero_products,
            'active_products': total_products - zero_products,
            'file_path': self.file_path
        }