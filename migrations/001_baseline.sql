-- 001_baseline.sql
-- ===================================================
-- الأساس: الجداول الثلاثة التي كانت تُنشأ سابقاً داخل
-- SQLiteRepository._init_db(). نُقلت هنا كما هي حرفياً حتى تصبح
-- الـ schema مملوكة للـ migrations وحدها (مصدر واحد للحقيقة).
--
-- IF NOT EXISTS مقصود: قواعد البيانات الموجودة مسبقاً (التي أنشأها
-- _init_db) تمرّ عبر هذا الملف دون خطأ ودون فقدان بيانات.
-- ===================================================

-- جدول الأشهر
CREATE TABLE IF NOT EXISTS months (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL
);

-- جدول المنتجات
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- جدول المبيعات
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    month_id INTEGER NOT NULL,
    quantity REAL NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (month_id) REFERENCES months(id) ON DELETE CASCADE,
    UNIQUE(product_id, month_id)
);

-- فهارس لتحسين الأداء
CREATE INDEX IF NOT EXISTS idx_sales_product ON sales(product_id);
CREATE INDEX IF NOT EXISTS idx_sales_month ON sales(month_id);
