-- 006_recommendations.sql
-- ===================================================
-- توصيات النظام الإنتاجية — يقابل domain.entities.ProductionRecommendation
-- مع RiskScore مدمجاً بداخله (كما في الكيان: recommendation.risk).
--
-- عوامل الخطورة الخمسة أعمدة منفصلة لا JSON، لأنها *يُستعلم عنها*:
-- "أرِني المنتجات التي خطورتها عالية بسبب تقلب الطلب تحديداً" سؤال
-- مشروع في Phase 4. (قارن مع forecasts حيث المصفوفات JSON لأنها
-- تُقرأ ككتلة — القاعدة واحدة: طبّع ما تستعلم عنه.)
--
-- risk_level غير مخزَّن — RiskScore.level خاصية محسوبة من score عبر
-- RiskLevel.from_score(). تخزينها يعني احتمال انحرافها عن مصدرها.
-- نفس المبدأ المطبَّق في inventory (needs_reorder).
--
-- forecast_id يربط التوصية بالتنبؤ الذي وُلّدت منه — أثر قابل للتتبّع
-- يجيب: "لماذا أوصى النظام بهذا الرقم؟"
-- ON DELETE SET NULL لا CASCADE: حذف تنبؤ قديم يجب ألا يمحو سجل
-- توصية اتُّخذ عليها قرار إنتاج فعلي.
-- ===================================================

CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    recommended_quantity REAL NOT NULL
        CHECK (recommended_quantity >= 0),
    reason TEXT NOT NULL,               -- "بسبب ارتفاع الطلب المتوقع بنسبة 18%"
    expected_demand_change_pct REAL NOT NULL,

    -- RiskScore المدمج (كلها NULL معاً إن لم تُحسب الخطورة)
    risk_score REAL
        CHECK (risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)),
    demand_volatility REAL,
    stock_depletion_risk REAL,
    forecast_accuracy_penalty REAL,
    seasonality_factor REAL,
    growth_rate REAL,

    forecast_id INTEGER,                -- التنبؤ الذي وُلّدت منه التوصية
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (forecast_id) REFERENCES forecasts(id) ON DELETE SET NULL
);

-- أحدث توصية لمنتج — الاستعلام الأساسي في لوحة التحكم
CREATE INDEX IF NOT EXISTS idx_recommendations_product
    ON recommendations(product_id, generated_at DESC);

-- "أرِني المنتجات عالية الخطورة" — فرز حسب الدرجة
CREATE INDEX IF NOT EXISTS idx_recommendations_risk
    ON recommendations(risk_score DESC, generated_at DESC);
