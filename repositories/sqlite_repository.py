# repositories/sqlite_repository.py
import sqlite3
import json
from typing import Tuple, List, Dict, Any
import config
from repositories.base import DataRepository, connect, resolve_db_path
from core.exceptions import MigrationError
from migrate import missing_tables

class SQLiteRepository(DataRepository):
    """تطبيق DataRepository باستخدام SQLite مع هيكل Normalized"""

    def __init__(self, db_path: str | None = None):
        self.db_path = resolve_db_path(db_path)
        self._verify_schema()
        # التحقق مما إذا كانت قاعدة البيانات فارغة (لا توجد بيانات)
        if not self._has_data():
            # إذا كانت فارغة، نقوم بالترحيل من JSON تلقائياً (لأول مرة)
            self.migrate_from_json()

    def _get_connection(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def _verify_schema(self):
        """التأكد من أن الـ migrations طُبِّقت — دون إنشاء أي شيء.

        المستودع لم يعد يملك بنية القاعدة (كان _init_db ينشئها هنا قبل
        Phase 2). ملفات migrations/ هي المالك الوحيد الآن، وهذه الدالة
        تتحقق فقط. الفشل هنا صريح ومع تعليمات، بدل انهيار لاحق برسالة
        "no such table" غامضة عند أول استعلام.
        """
        missing = missing_tables(self.db_path)
        if missing:
            raise MigrationError(
                f"قاعدة البيانات ناقصة {len(missing)} جدول. "
                f"شغّل: python migrate.py",
                context={"db_path": self.db_path, "missing_tables": missing},
            )

    def _has_data(self) -> bool:
        """التحقق مما إذا كانت قاعدة البيانات تحتوي على بيانات (جدول sales ليس فارغاً)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sales")
            count = cursor.fetchone()[0]
            return count > 0
    
    def migrate_from_json(self) -> None:
        """
        ترحيل البيانات من JSON إلى SQLite مع التحقق من السلامة.
        - حذف جميع البيانات الحالية (إن وجدت).
        - قراءة JSON.
        - إدراج الأشهر، المنتجات، والمبيعات.
        - التحقق من صحة البيانات بعد الترحيل.
        """
        # 1. قراءة JSON — عبر سمة الوحدة لا نسخة مجمَّدة عند الاستيراد
        with open(config.DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        months_list = data['months']
        products_dict = data['products']
        # اختياري: {اسم المنتج: فئته} — لا يُخترَع؛ من مصدر حقيقي واحد
        # اليوم (scripts/generate_demo_data.py، الذي يعرف تركيب FAMILIES
        # فعلاً وقت التوليد). ملف JSON بلا هذا المفتاح (بيانات قديمة، أو
        # اختبارات) يمرّ بلا فئات — لا خطأ.
        categories = data.get('categories', {})

        # 2. حذف البيانات القديمة (إذا وجدت) لإعادة الترحيل النظيف
        # products_meta لا تُذكر هنا: ON DELETE CASCADE على product_id يمحوها
        # مع حذف products (PRAGMA foreign_keys=ON مفعَّل في _get_connection).
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sales")
            cursor.execute("DELETE FROM products")
            cursor.execute("DELETE FROM months")
            conn.commit()
        
        # 3. إدراج الأشهر
        month_id_map = {}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for idx, month_name in enumerate(months_list):
                cursor.execute(
                    "INSERT INTO months (name, sort_order) VALUES (?, ?)",
                    (month_name, idx)
                )
                month_id_map[month_name] = cursor.lastrowid
            conn.commit()
        
        # 4. إدراج المنتجات والمبيعات
        product_id_map = {}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for product_name, quantities in products_dict.items():
                # إدراج المنتج
                cursor.execute(
                    "INSERT INTO products (name) VALUES (?)",
                    (product_name,)
                )
                product_id = cursor.lastrowid
                product_id_map[product_name] = product_id
                
                # إدراج المبيعات لهذا المنتج
                for month_name, quantity in zip(months_list, quantities):
                    month_id = month_id_map[month_name]
                    cursor.execute(
                        "INSERT INTO sales (product_id, month_id, quantity) VALUES (?, ?, ?)",
                        (product_id, month_id, quantity)
                    )

                # الفئة إن وُجدت — منتج بلا فئة في المصدر يبقى بلا سجل
                # products_meta أصلاً، لا صفّاً بفئة NULL مُنشأً عبثاً
                category = categories.get(product_name)
                if category is not None:
                    cursor.execute(
                        "INSERT INTO products_meta (product_id, category) VALUES (?, ?)",
                        (product_id, category)
                    )
            conn.commit()

        # 5. التحقق من سلامة البيانات
        valid = self._validate_migration(months_list, products_dict)
        if not valid:
            raise RuntimeError("فشل التحقق من سلامة البيانات بعد الترحيل من JSON إلى SQLite")
    
    def _validate_migration(self, original_months: List[str], original_products: Dict[str, List[float]]) -> bool:
        """التحقق من تطابق البيانات بعد الترحيل مع المصدر الأصلي"""
        # مقارنة عدد الأشهر
        db_months = self.get_months()
        if db_months != original_months:
            return False
        
        # مقارنة عدد المنتجات
        db_products = self.get_products()
        if set(db_products) != set(original_products.keys()):
            return False
        
        # مقارنة البيانات الكمية لكل منتج
        for product_name in original_products.keys():
            original_data = original_products[product_name]
            db_data = self.get_product_data(product_name)
            if len(db_data) != len(original_data):
                return False
            # مقارنة القيم مع تسامح بسيط للفروق العددية
            for o, d in zip(original_data, db_data):
                if abs(o - d) > 1e-9:
                    return False
        return True
    
    def load_data(self) -> Tuple[List[str], Dict[str, List[float]]]:
        """
        تحميل جميع البيانات من SQLite وإرجاعها بنفس شكل JSON
        (months: list, products: dict{product_name: [quantities]})
        """
        months = self.get_months()
        products = {}
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # استعلام لجلب جميع المبيعات مع أسماء المنتجات والأشهر بالترتيب
            cursor.execute("""
                SELECT p.name AS product_name, m.name AS month_name, s.quantity
                FROM sales s
                JOIN products p ON s.product_id = p.id
                JOIN months m ON s.month_id = m.id
                ORDER BY p.id, m.sort_order
            """)
            rows = cursor.fetchall()
            
            # تجميع البيانات حسب المنتج
            current_product = None
            current_data = []
            for row in rows:
                if current_product is None:
                    current_product = row['product_name']
                if row['product_name'] != current_product:
                    products[current_product] = current_data
                    current_product = row['product_name']
                    current_data = []
                current_data.append(row['quantity'])
            if current_product is not None:
                products[current_product] = current_data
        
        return months, products
    
    def get_products(self) -> List[str]:
        """إرجاع قائمة بأسماء المنتجات مرتبة أبجدياً"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM products ORDER BY name")
            rows = cursor.fetchall()
            return [row['name'] for row in rows]
    
    def get_months(self) -> List[str]:
        """إرجاع قائمة الأشهر بالترتيب الزمني"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM months ORDER BY sort_order")
            rows = cursor.fetchall()
            return [row['name'] for row in rows]
    
    def get_product_data(self, product_name: str) -> List[float]:
        """إرجاع بيانات منتج محدد (قائمة الكميات حسب ترتيب الأشهر)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.quantity
                FROM sales s
                JOIN products p ON s.product_id = p.id
                JOIN months m ON s.month_id = m.id
                WHERE p.name = ?
                ORDER BY m.sort_order
            """, (product_name,))
            rows = cursor.fetchall()
            return [row['quantity'] for row in rows]
    
    def save_data(self, months: List[str], products: Dict[str, List[float]]) -> None:
        """
        حفظ البيانات بالكامل (يستخدم للترحيل العكسي أو التحديث)
        هذه الدالة تستخدم للتوافق مع الواجهة، لكننا نفضل استخدام migrate_from_json
        """
        # حذف البيانات القديمة وإعادة إدراجها
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sales")
            cursor.execute("DELETE FROM products")
            cursor.execute("DELETE FROM months")
            
            # إدراج الأشهر
            month_id_map = {}
            for idx, month_name in enumerate(months):
                cursor.execute(
                    "INSERT INTO months (name, sort_order) VALUES (?, ?)",
                    (month_name, idx)
                )
                month_id_map[month_name] = cursor.lastrowid
            
            # إدراج المنتجات والمبيعات
            for product_name, quantities in products.items():
                cursor.execute(
                    "INSERT INTO products (name) VALUES (?)",
                    (product_name,)
                )
                product_id = cursor.lastrowid
                for month_name, quantity in zip(months, quantities):
                    month_id = month_id_map[month_name]
                    cursor.execute(
                        "INSERT INTO sales (product_id, month_id, quantity) VALUES (?, ?, ?)",
                        (product_id, month_id, quantity)
                    )
            conn.commit()
    
    def get_categories(self) -> Dict[str, str]:
        """{اسم المنتج: فئته} — لمن يملك سجل products_meta.category فعلياً.

        JOIN لا LEFT JOIN: منتج بلا سجل وصفي (أو بفئة NULL) لا يظهر هنا
        إطلاقاً، فيُستبعد من كل تجميع فئوي بدل أن يظهر بفئة وهمية.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.name AS product_name, pm.category
                FROM products_meta pm
                JOIN products p ON pm.product_id = p.id
                WHERE pm.category IS NOT NULL
            """)
            return {row['product_name']: row['category'] for row in cursor.fetchall()}

    def get_metadata(self) -> Dict[str, Any]:
        """الحصول على معلومات وصفية عن البيانات من قاعدة البيانات"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # عدد المنتجات
            cursor.execute("SELECT COUNT(*) FROM products")
            total_products = cursor.fetchone()[0]
            
            # عدد الأشهر
            cursor.execute("SELECT COUNT(*) FROM months")
            total_months = cursor.fetchone()[0]
            
            # عدد المنتجات التي جميع قيمها صفر (لا توجد مبيعات)
            cursor.execute("""
                SELECT COUNT(DISTINCT p.id)
                FROM products p
                LEFT JOIN sales s ON p.id = s.product_id
                GROUP BY p.id
                HAVING COALESCE(SUM(s.quantity), 0) = 0
            """)
            zero_products = len(cursor.fetchall())
            
            return {
                'total_products': total_products,
                'total_months': total_months,
                'zero_products': zero_products,
                'active_products': total_products - zero_products,
                'db_path': self.db_path
            }