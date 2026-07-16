# ARCHITECTURE.md

## المعمارية الحالية (قبل التطوير)

```
app.py (composition root)
 ├─ repositories/        Data Access — نظيف، Repository Pattern سليم
 │   ├─ base.py           (ABC)
 │   ├─ json_repository.py
 │   ├─ sqlite_repository.py
 │   └─ factory.py
 ├─ services/analytics.py  حسابات + تجهيز عرض (مخلوطة جزئياً)
 ├─ models/
 │   ├─ forecasting.py    ETS + SARIMA (منطق معقد داخل دالتين طويلتين)
 │   └─ statistics.py     trend + outliers
 └─ ui/                    Streamlit views تستدعي models مباشرة
     ├─ sidebar.py, dashboard.py, charts.py, tables.py, export.py
```

**المشكلة الأساسية:** لا توجد طبقة Domain ولا Service Layer حقيقية تفصل
"ماذا نُقرر" (business logic) عن "كيف نعرضه" (UI) و"من أين نجلبه"
(repositories). `ui/dashboard.py` يستدعي `models.forecasting` مباشرة،
مما يجعل استبدال أو مقارنة نماذج (Prophet, XGBoost...) لاحقاً مكلفاً.

## المعمارية المستهدفة (بعد اكتمال كل المراحل)

```
app.py
 ├─ core/                   ✅ (Phase 0 — مُنفَّذ)
 │   ├─ app_config.py        إعدادات بدون side effects + دعم env vars
 │   ├─ logging_config.py    logging مركزي (console + rotating file)
 │   └─ exceptions.py        تسلسل استثناءات موحّد
 ├─ domain/                 ✅ (Phase 0 — الهيكل فقط، المنطق لاحقاً)
 │   └─ entities.py          ForecastResult, RiskScore,
 │                           ProductionRecommendation, InventoryStatus
 ├─ repositories/            (بدون تغيير جوهري + إضافة جداول جديدة Phase 2)
 ├─ services/
 │   ├─ forecast_engine/     (Phase 3) ETS/SARIMA/Prophet/XGBoost/RF + اختيار تلقائي
 │   ├─ decision_engine/     (Phase 4) توصيات الإنتاج
 │   ├─ inventory_service/   (Phase 5) Reorder Point, Safety Stock
 │   └─ risk_service/        (Phase 4) Risk Score
 └─ ui/
     ├─ pages/executive.py         (Phase 6)
     ├─ pages/forecasting.py       (Phase 6)
     ├─ pages/production_planning.py (Phase 6)
     └─ pages/product_intelligence.py (Phase 6)
```

## مبدأ الدمج: بدون Big Bang

كل مرحلة تُضاف كطبقة **جديدة** بجانب الكود الحالي، ولا تُعدَّل الوحدات
القديمة إلا عند الحاجة الفعلية (مثال: `ui/dashboard.py` سيبقى يعمل حرفياً
كما هو حتى المرحلة 6، حين تُستبدل صفحاته تدريجياً بصفحات `ui/pages/`).

هذا يعني أن المشروع **يبقى قابلاً للتشغيل والاختبار في كل مرحلة**، بدل أن
يتحول لإعادة بناء كاملة معلّقة.
