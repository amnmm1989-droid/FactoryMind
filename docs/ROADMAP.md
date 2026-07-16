# ROADMAP.md
نظام تحليل وتنبؤ أوامر التصنيع → Manufacturing Decision Support System

## Phase 0 — Foundation ✅ (مُنفَّذة في هذا الرد)
**الهدف:** أساس صلب لا يعتمد عليه شيء آخر لكن كل شيء آخر يعتمد عليه.

- [x] `core/app_config.py` — إعدادات بدون side effects + دعم متغيرات البيئة
- [x] `core/logging_config.py` — logging مركزي (console + rotating file)
- [x] `core/exceptions.py` — تسلسل استثناءات موحّد
- [x] `domain/entities.py` — هيكل الكائنات (ForecastResult, RiskScore,
      ProductionRecommendation, InventoryStatus) — بدون منطق أعمال بعد
- [x] 12 اختبار وحدة (`tests/test_phase0_foundation.py`) — **جميعها ناجحة**
- [x] لا كسر لأي كود موجود (config.py, app.py, ... تعمل كما هي)

**معيار القبول:** `pytest tests/test_phase0_foundation.py` أخضر بالكامل. ✅ تحقق.

---

## Phase 1 — Domain + Service Layer Refactor ✅
- استخراج منطق `ui/dashboard.py` (compute stats, forecast orchestration)
  إلى `services/product_analysis_service.py` يُرجع `domain.entities` بدل
  قواميس خام.
- تحويل `models/forecasting.py` لرفع `InsufficientDataError` /
  `ModelTrainingError` بدل ابتلاع الاستثناءات.
- ربط `core.logging_config` بكل نقاط الفشل الحالية (`except Exception as e`).
- **لا تغيير على واجهة Streamlit المرئية.**

---

## Phase 2 — DB Schema Extension ✅
**الهدف:** نقل ملكية بنية القاعدة من كود بايثون إلى migrations صريحة،
وتجهيز الجداول التي ستحتاجها المراحل 3-5.

- [x] `migrations/001_baseline.sql` — الجداول الثلاثة القائمة
      (months, products, sales)، منقولة حرفياً من `_init_db()`
- [x] `migrations/002_products_meta.sql` — بيانات المنتجات الوصفية
- [x] `migrations/003_inventory.sql` — يقابل `InventoryStatus`
- [x] `migrations/004_forecasts.sql` — يقابل `ForecastResult`
- [x] `migrations/005_model_performance.sql` — تقييم النماذج (Phase 3)
- [x] `migrations/006_recommendations.sql` — يقابل `ProductionRecommendation`
      مع `RiskScore` مدمجاً (Phase 4)
- [x] `migrations/007_production_plans.sql` — قرارات الإنتاج الفعلية
- [x] `migrate.py` — مشغّل idempotent وذرّي، مع كشف تعديل الـ migrations
      المطبَّقة (checksum) وأمر `--status`
- [x] `SQLiteRepository._init_db()` **أُزيل** — استُبدل بـ `_verify_schema()`
      يرفع `MigrationError` مع تعليمات واضحة بدل إنشاء الجداول ضمناً
- [x] `tests/conftest.py` — الاختبارات على قاعدة مؤقتة، لا على `data/app.db`
- [x] 19 اختبار (`tests/test_migrations.py`) — **جميعها ناجحة**

**معيار القبول:** `pytest` أخضر بالكامل (48 اختباراً)، و`python migrate.py`
يعمل مراراً بلا أثر جانبي، ويرقّي قاعدة بيانات قائمة دون فقدان صف. ✅ تحقق.

**تغيير سلوكي:** التطبيق لم يعد ينشئ الجداول تلقائياً — `python migrate.py`
مطلوب مرة واحدة قبل أول تشغيل. راجع `docs/MIGRATION_GUIDE_PHASE2.md`.

---

## Phase 3 — Forecast Engine ✅
**الهدف:** واجهة موحّدة تدرّب عدة نماذج، تقيّمها، وتختار الأفضل بالأدلة.

- [x] `services/forecast_engine/base.py` — عقد `Forecaster` + `ForecastOutput`
- [x] `naive.py` — **Naive + MovingAverage** (إضافة على الخطة، انظر أدناه)
- [x] `statistical.py` — ETS + SARIMA (تنفيذ صريح، يفشل بصوت مسموع)
- [x] `prophet_model.py` — Prophet (استيراد كسول)
- [x] `tree.py` — XGBoost + RandomForest عبر lag features
- [x] `evaluation.py` — backtesting + MAE/RMSE/MAPE
- [x] `cache.py` — تخزين مؤقت بمفتاح hash(product+data+model+horizon)
- [x] `registry.py` + `engine.py` — الاختيار الآلي
- [x] `repositories/forecast_repository.py` — الحفظ في جداول Phase 2
- [x] `migrations/008` — ربط model_performance بجولة التقييم
- [x] 69 اختباراً (`test_forecast_engine.py` + `test_forecast_repository.py`)

**معيار القبول:** `pytest` أخضر بالكامل (117 اختباراً). ✅ تحقق.

### إضافتان على الخطة الأصلية — ولماذا

**1. نموذجا أساس (Naive + MovingAverage).** الخطة طلبت 5 نماذج تحتاج
كلها ≥24 نقطة. لكن وسيط منتجات هذا المشروع **9 أشهر غير صفرية من 44**،
و72 من 185 منتجاً لها 1-5 أشهر فقط. بلا أساس، المحرك يفشل على 39% من
الكتالوج — ولا يوجد مرجع يُقاس عليه هل تستحق النماذج المعقّدة تعقيدها.

**2. قياس على النقاط غير الصفرية لا طول السلسلة.** كل منتج له 44 نقطة
بالضبط، فمعيار الطول وحده يقول إن كل المنتجات صالحة لـ SARIMA. ليست كذلك.

### النتيجة القياسية (43 منتجاً لها ≥24 شهراً غير صفري)

| النموذج | مرات الفوز | متوسط الترتيب |
|---|---|---|
| MovingAverage | 10 | **2.47** |
| Naive | **16** | 3.05 |
| RandomForest | 6 | 3.65 |
| XGBoost | 8 | 4.16 |
| ETS | 1 | 4.63 |
| Prophet | **0** | 4.81 |
| SARIMA | 2 | 5.23 |

**النماذج الساذجة تفوز في 60% من الحالات على أغنى البيانات المتاحة.**
Prophet لم يفز ولا مرة. هذا ليس عيباً في التنفيذ — إنه ما تقوله البيانات:
44 نقطة شهرية لا تكفي لتعلّم أنماط معقّدة. القيمة الحقيقية لهذه المرحلة
هي أن النظام صار **يعرف ذلك ويقيسه**، بدل افتراض أن الأعقد أفضل.

### انحرافات موثّقة

- **الـ cache يخزّن النتيجة لا النموذج.** الخطة طلبت تخليل النموذج
  (joblib). كائنات Prophet/statsmodels المخلَّلة مرتبطة بإصدار المكتبة —
  ترقية واحدة تجعل كل ملف قنبلة موقوتة تُحمَّل وتتصرف بصمت بشكل مختلف.
  تخزين النتيجة يتجنّب التدريب *والتنبؤ*، ويزن كيلوبايتات بدل ميغابايتات.

### غير منجَز بعد (خارج نطاق هذه المرحلة)

- **المحرك غير موصول بـ `ui/dashboard.py`** — الواجهة ما زالت تستدعي
  `services/product_analysis_service.py` (مسار Phase 1). الوصل في Phase 6.
- `models/forecasting.py` لم يُمسّ — يبقى لأن الواجهة والاختبارات عليه.

---

## Phase 4 — Decision Engine + Risk Scoring (التالية)
`services/decision_engine/`: يحوّل `ForecastResult` إلى
`ProductionRecommendation` (الصيغة المطلوبة: "يوصى بإنتاج X وحدة...").
`services/risk_service/`: يحسب `RiskScore` من (تقلب الطلب، نفاد
المخزون، دقة التنبؤ، الموسمية، معدل النمو) → 0-100.

## Phase 5 — Inventory Module
`services/inventory_service/`: Reorder Point = (متوسط الاستهلاك اليومي
× Lead Time) + Safety Stock. تنبيهات نفاد ومقترحات كمية إعادة الطلب.

## Phase 6 — Dashboard إعادة تصميم لمدير الإنتاج
4 صفحات جديدة (Executive / Forecasting / Production Planning /
Product Intelligence) تستهلك services من Phase 1-5. الصفحة الحالية
تبقى متاحة كـ "Advanced Analytics View" للمحلل.

## Phase 7 — AI Explainer + Export احترافي
Assistant يستعلم فعلياً من `domain.entities` المحسوبة (ليس LLM عام) +
PDF (via reportlab/weasyprint) + Excel محسّن (تنسيق شرطي، رسوم مضمّنة).

## Phase 8 — Tests + CI (مستمر بالتوازي مع كل مرحلة أعلاه)
كل مرحلة تُضيف اختباراتها الخاصة كما فعلنا في Phase 0. لا مرحلة تُعتبر
"منتهية" بدون اختبارات خضراء.

---

## كيف تختار من أين نكمل؟
أخبرني برقم المرحلة (1 إلى 8) وسأبدأ التنفيذ الفعلي بنفس الأسلوب:
كود حقيقي + اختبارات تعمل + توثيق للتغيير، بدون المساس بما يعمل حالياً.
