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
 │   ├─ logging_config.py    logging مركزي (console + rotating file)
 │   ├─ exceptions.py        تسلسل استثناءات موحّد
 │   └─ runtime_mode.py      محلي (يحفظ) | مستضاف (لا يحفظ)
 ├─ domain/                 ✅ (Phase 0 — الهيكل فقط، المنطق لاحقاً)
 │   └─ entities.py          ForecastResult, RiskScore,
 │                           ProductionRecommendation, InventoryStatus
 ├─ migrations/             ✅ (Phase 2 — مُنفَّذ)
 │   └─ NNN_*.sql            المالك الوحيد لبنية القاعدة، يطبّقها migrate.py
 ├─ repositories/            (Repository Pattern كما هو — لكنه لم يعد
 │                           يملك الـ schema، يتحقق منها فقط)
 ├─ services/
 │   ├─ forecast_engine/     ✅ (Phase 3 — مُنفَّذ) 9 نماذج + اختيار بالأدلة:
 │   │                       Naive/MovingAverage/Croston/TSB/ETS/SARIMA/
 │   │                       Prophet/XGBoost/RF. المحرك لا يعرف نموذجاً
 │   │                       بالاسم — registry.py فقط.
 │   │                       intermittent.py يصنّف السلسلة (ADI/CV²)
 │   │                       ويحدد مقياس الاختيار: 84% من الكتالوج متقطّع.
 │   │                       ⚠️ غير موصول بـ ui/ بعد (الوصل في Phase 6)
 │   ├─ decision_engine/     ✅ (Phase 4) ForecastResult -> ProductionRecommendation
 │   │                       الكمية = الطلب المتوقع ناقص المخزون المتاح
 │   ├─ ingest.py            ✅ قراءة تقارير ERP (CSV/Excel). المدخل الوحيد
 │   │                       لبيانات المستخدم. ⚠️ يقرأ شكلاً واحداً:
 │   │                       منتج × شهر. كل مدير جديد = شكل ملف جديد.
 │   └─ risk_service/        ✅ (Phase 4) RiskScore من 5 عوامل.
 │                           عامل بلا بيانات = None لا صفر، ويُستبعد
 │                           من الحساب مع إعادة موازنة الباقي.
 └─ ui/
     ├─ i18n.py               ✅ الترجمة (عربي/إنجليزي). كل نص يراه
     │                        المستخدم يمرّ منه. الخدمات ترفع *رموزاً*
     │                        (ReasonPart, Warning_, code) لا نصوصاً —
     │                        الطبقة التي تحسب لا تقرر لغة العرض.
     ├─ data_source.py        بيانات الجلسة: ملف المستخدم أو العرض
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

---

## موقع المشروع: طبقة تحليل لا نظام تشغيل

```
   ┌─────────────┐   تصدير    ┌──────────────┐
   │  Odoo/SAP   │  ────────► │  FactoryMind │
   │ (نظام السجل)│   CSV/XLSX │  (تحليل فقط) │
   └─────────────┘            └──────────────┘
         ▲                            │
         └────── الإنسان يقرر ────────┘
```

**اتجاه واحد.** لا كتابة في ERP، ولا API، ولا إنشاء أوامر. السبب ليس
تقنياً: تحليل خاطئ = اقتراح يُرفَض، وأمر خاطئ = مال مصروف. الأداة لا
تستحق تلك المسؤولية ما دامت — بشهادة قياساتها نفسها — تعجز عن التنبؤ بـ84%
من الكتالوج.

`recommendations` (اقتراح النظام) منفصل عن `production_plans` (قرار
الإنسان) منذ Phase 2 لهذا السبب بالضبط.

## قاعدة الطبقات — تعلّمناها بالخطأ

**الطبقة التي تحسب لا تقرر لغة العرض ولا صيغته.**

خُرقت هذه القاعدة في أربعة مواضع، وكشفتها إضافة الإنجليزية:
`domain/entities` كان يبني جملة التوصية، و`decision_engine` نص السبب،
و`models/statistics` يُرجع `"📈 صاعد"` كقيمة، و`analytics` يستخدم `'الربع 1'`
مفتاحَ فرز.

كلها تُصدر **رموزاً** الآن (`ReasonPart`، `message_code`، `q1..q4`)،
و`ui/i18n.py` وحده يعرف اللغات. أي طبقة تكتب نصاً للمستخدم خارج `ui/`
تُعيد الخطأ.
