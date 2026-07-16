-- 004_forecasts.sql
-- ===================================================
-- نتائج التنبؤ المحفوظة — يقابل domain.entities.ForecastResult.
--
-- قرار تصميمي: forecast_values / lower_bound / upper_bound تُخزَّن
-- كمصفوفات JSON في عمود واحد، لا كجدول نقاط منفصل (forecast_points).
--
-- السبب: ForecastResult يحمل قوائم تُقرأ وتُكتب ككتلة واحدة دائماً —
-- لا يوجد استعلام يطلب "الخطوة الثالثة فقط". التطبيع هنا كان سينتج
-- جدولاً بملايين الصفوف (185 منتج × 5 نماذج × 24 خطوة × كل إعادة
-- تدريب) مقابل صفر مكاسب استعلامية.
--
-- في المقابل مقاييس الدقة (mae/rmse/mape) أعمدة حقيقية — لأنها
-- *يُستعلم عنها* فعلاً: ترتيب النماذج، تتبّع الدقة عبر الزمن،
-- واختيار الأفضل في Phase 3.
--
-- CHECK على صحة JSON يمنع كتابة نص تالف بصمت.
--
-- data_hash = hash(product + input data) — مفتاح الـ cache في Phase 3،
-- يسمح بمعرفة ما إذا كان تنبؤ محفوظ ما زال صالحاً لنفس البيانات.
-- ===================================================

CREATE TABLE IF NOT EXISTS forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    model_name TEXT NOT NULL,           -- ETS / SARIMA / Prophet / XGBoost / RF
    horizon INTEGER NOT NULL
        CHECK (horizon > 0),            -- عدد خطوات التنبؤ
    forecast_values TEXT NOT NULL
        CHECK (json_valid(forecast_values)),
    lower_bound TEXT NOT NULL
        CHECK (json_valid(lower_bound)),
    upper_bound TEXT NOT NULL
        CHECK (json_valid(upper_bound)),
    mae REAL CHECK (mae IS NULL OR mae >= 0),
    rmse REAL CHECK (rmse IS NULL OR rmse >= 0),
    mape REAL CHECK (mape IS NULL OR mape >= 0),
    data_hash TEXT,                     -- مفتاح cache: hash(product+data)
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

-- أحدث تنبؤ لمنتج+نموذج — الاستعلام الأكثر شيوعاً في Phase 3
CREATE INDEX IF NOT EXISTS idx_forecasts_product_model
    ON forecasts(product_id, model_name, generated_at DESC);

-- البحث عن تنبؤ صالح في الـ cache
CREATE INDEX IF NOT EXISTS idx_forecasts_hash
    ON forecasts(data_hash);
