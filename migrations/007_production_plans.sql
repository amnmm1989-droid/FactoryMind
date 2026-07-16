-- 007_production_plans.sql
-- ===================================================
-- خطط الإنتاج: ما تقرّر إنتاجه فعلاً من كل منتج في شهر معيّن.
--
-- الفرق عن recommendations (006): هذا الجدول يحمل *قرار الإنسان*،
-- بينما recommendations يحمل *اقتراح النظام*. قد يوافق المخطِّط على
-- التوصية أو يخالفها — والفصل يسمح لاحقاً بقياس: كم مرة تُتَّبع
-- توصياتنا؟ وهل النتائج أفضل حين تُتَّبع؟ دمجهما كان سيمحو هذا السؤال.
--
-- يأتي بعد 006 لأن source_recommendation_id يشير إلى recommendations —
-- والمفتاح الأجنبي يحتاج الجدول المشار إليه موجوداً.
--
-- month_id يشير إلى months الموجود — الخطط مرتبطة بنفس المحور الزمني
-- الذي تُقاس عليه المبيعات، لا بمحور مستقل.
--
-- actual_quantity يُملأ بعد التنفيذ — الفارق بينه وبين planned_quantity
-- هو ما يقيس جودة التخطيط.
-- ===================================================

CREATE TABLE IF NOT EXISTS production_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    month_id INTEGER NOT NULL,
    planned_quantity REAL NOT NULL
        CHECK (planned_quantity >= 0),
    actual_quantity REAL
        CHECK (actual_quantity IS NULL OR actual_quantity >= 0),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'approved', 'in_progress', 'completed', 'cancelled')),
    source_recommendation_id INTEGER,   -- التوصية التي بُنيت عليها (إن وُجدت)
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (month_id) REFERENCES months(id) ON DELETE CASCADE,
    FOREIGN KEY (source_recommendation_id) REFERENCES recommendations(id) ON DELETE SET NULL,
    UNIQUE(product_id, month_id)
);

CREATE INDEX IF NOT EXISTS idx_production_plans_month
    ON production_plans(month_id, status);

CREATE INDEX IF NOT EXISTS idx_production_plans_product
    ON production_plans(product_id);
