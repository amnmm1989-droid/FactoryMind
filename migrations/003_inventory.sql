-- 003_inventory.sql
-- ===================================================
-- حالة المخزون الحالية لكل منتج — يقابل domain.entities.InventoryStatus
-- عموداً بعمود (current_stock, minimum_stock, safety_stock,
-- reorder_point, lead_time_days) ليُبنى الكائن من الصف مباشرة في Phase 5.
--
-- ملاحظة: needs_reorder و stockout_risk خاصيتان محسوبتان في الكيان
-- (properties)، فلا تُخزَّنان هنا — تخزين قيمة محسوبة يعني احتمال
-- تعارضها مع مصدرها.
--
-- هذا الجدول يحمل *الحالة الآنية* فقط (صف واحد لكل منتج). تاريخ حركة
-- المخزون خارج نطاق Phase 2.
-- ===================================================

CREATE TABLE IF NOT EXISTS inventory (
    product_id INTEGER PRIMARY KEY,
    current_stock REAL NOT NULL DEFAULT 0
        CHECK (current_stock >= 0),
    minimum_stock REAL NOT NULL DEFAULT 0
        CHECK (minimum_stock >= 0),
    safety_stock REAL NOT NULL DEFAULT 0
        CHECK (safety_stock >= 0),
    reorder_point REAL NOT NULL DEFAULT 0
        CHECK (reorder_point >= 0),
    lead_time_days INTEGER NOT NULL DEFAULT 0
        CHECK (lead_time_days >= 0),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

-- للاستعلام عن المنتجات التي تحتاج إعادة طلب دون مسح الجدول كاملاً
CREATE INDEX IF NOT EXISTS idx_inventory_reorder
    ON inventory(current_stock, reorder_point);
