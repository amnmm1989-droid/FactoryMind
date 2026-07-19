# repositories/base.py
import sqlite3
from abc import ABC, abstractmethod
from typing import Tuple, List, Dict, Any, Optional

import config
from core.exceptions import DataAccessError


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


def connect(db_path: str) -> sqlite3.Connection:
    """اتصال بإعدادات هذا المشروع الثابتة.

    كانت هذه الأسطر الأربعة منسوخة حرفياً في ثلاثة مستودعات. الخطر ليس
    التكرار بذاته بل **الانحراف الصامت**: `PRAGMA foreign_keys = ON` قيد
    نزاهةٍ لا تفضيل أسلوبي — سطر واحد يسقط من نسخة واحدة يعني مستودعاً
    يكتب صفوفاً يتيمة بلا اعتراض، ولا اختبار يلتقط ذلك لأن كل مستودع
    يُختبر وحده. بيتٌ واحد يجعل السقوط مستحيلاً لا مستبعَداً.

    row_factory للوصول بالأسماء: كل استعلام هنا يقرأ row["id"] لا row[0].
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def product_id(conn: sqlite3.Connection, product_name: str) -> int:
    """معرّف المنتج، أو خطأ صريح.

    الغياب يرفع ولا يُرجع None: من يستدعيها يكتب صفّاً يشير إلى هذا
    المعرّف، وNone هناك تصبح صفّاً يتيماً أو انهياراً بعيداً عن السبب.
    """
    row = conn.execute(
        "SELECT id FROM products WHERE name = ?", (product_name,)
    ).fetchone()
    if row is None:
        raise DataAccessError(
            f"منتج غير موجود في قاعدة البيانات: {product_name}",
            context={"product": product_name},
        )
    return row["id"]


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

    def get_categories(self) -> Dict[str, str]:
        """فئة كل منتج، لمن يحمل فئات فعلية لا تخميناً.

        غير مجرَّدة عمداً: قدرة اختيارية لا جزء من العقد الأساسي. الافتراضي
        {} — منتَج بلا فئة معروفة يُستبعد من كل تجميع فئوي، لا يُحتسب في
        فئة "أخرى" مخترعة (services/reconciliation.py). SQLiteRepository
        يُعيد تعريفها من products_meta.category؛ JsonRepository (مسار قديم
        غير مُستخدَم فعلياً — DATA_SOURCE='sqlite' دائماً) يبقى على هذا
        الافتراضي بصدق: لا فئات في تلك البنية أصلاً.
        """
        return {}