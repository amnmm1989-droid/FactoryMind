-- 005_model_performance.sql
-- ===================================================
-- سجل تقييم النماذج — أساس "تقيّم كل واحد (MAE/RMSE/MAPE)، تختار
-- الأفضل" في Phase 3.
--
-- لماذا منفصل عن forecasts رغم تشابه الأعمدة؟
-- forecasts يجيب: "ما هو التنبؤ؟" — صف لكل تنبؤ مُنتَج ومحفوظ.
-- model_performance يجيب: "أي نموذج أدق لهذا المنتج؟" — صف لكل
-- تقييم، بما فيها نماذج جُرّبت وخسرت فلم يُحفظ لها تنبؤ أصلاً.
-- دمجهما كان سيخلط سجل القرار بنتيجة القرار.
--
-- is_best يوضّح أي نموذج فاز في جولة تقييم معيّنة (نفس evaluated_at
-- و data_hash) — لا يُفرض عبر قيد لأن SQLite لا يدعم partial unique
-- constraints بالمرونة المطلوبة هنا؛ يُدار في طبقة الخدمة.
-- ===================================================

CREATE TABLE IF NOT EXISTS model_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    mae REAL CHECK (mae IS NULL OR mae >= 0),
    rmse REAL CHECK (rmse IS NULL OR rmse >= 0),
    mape REAL CHECK (mape IS NULL OR mape >= 0),
    training_duration_ms INTEGER
        CHECK (training_duration_ms IS NULL OR training_duration_ms >= 0),
    is_best INTEGER NOT NULL DEFAULT 0
        CHECK (is_best IN (0, 1)),
    data_hash TEXT,                     -- يربط التقييم بالبيانات التي جرى عليها
    evaluated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

-- "أي نموذج هو الأفضل لهذا المنتج الآن؟"
CREATE INDEX IF NOT EXISTS idx_model_perf_best
    ON model_performance(product_id, is_best, evaluated_at DESC);

-- تتبّع أداء نموذج معيّن عبر الزمن
CREATE INDEX IF NOT EXISTS idx_model_perf_product_model
    ON model_performance(product_id, model_name, evaluated_at DESC);
