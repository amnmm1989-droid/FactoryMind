-- 002_products_meta.sql
-- ===================================================
-- بيانات وصفية للمنتجات: كل ما ليس كمية مبيعات.
-- جدول products الحالي يحمل الاسم فقط (id, name) — وتوسيعه مباشرة
-- كان سيجبر كل صف على حمل أعمدة قد تبقى فارغة. الفصل هنا يبقي
-- products نظيفاً ويسمح بوجود منتجات بلا بيانات وصفية بعد.
--
-- علاقة 1:1 مع products عبر product_id كمفتاح أساسي — منتج واحد
-- لا يملك أكثر من سجل وصفي واحد.
-- ===================================================

CREATE TABLE IF NOT EXISTS products_meta (
    product_id INTEGER PRIMARY KEY,
    category TEXT,                      -- تصنيف المنتج (مثال: أكياس، علب)
    unit TEXT NOT NULL DEFAULT 'وحدة',  -- وحدة القياس
    unit_cost REAL CHECK (unit_cost IS NULL OR unit_cost >= 0),
    lead_time_days INTEGER NOT NULL DEFAULT 0
        CHECK (lead_time_days >= 0),    -- مهلة التوريد (يُستخدم في Phase 5)
    min_order_quantity REAL NOT NULL DEFAULT 0
        CHECK (min_order_quantity >= 0),
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_products_meta_category ON products_meta(category);
CREATE INDEX IF NOT EXISTS idx_products_meta_active ON products_meta(is_active);
