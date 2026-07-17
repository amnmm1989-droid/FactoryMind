# الجزء 4 — الملحق التقني والمصادر

صيغ دقيقة لمن يبني مرحلة بعينها من `READINESS_3_PLAN.md`، ومصادر كل ادّعاء
بحثي في الأجزاء السابقة.

## الصيغ

### WAPE — Weighted Absolute Percentage Error

```
WAPE = Σ|actual - predicted| / Σ|actual|
```

الفرق عن MAPE: المقام مجموع لا متوسط نسب فردية — فمنتج بقيمة فعلية صغيرة
لا يُفجِّر المقياس كما يفعل في MAPE (وهو بالضبط سبب حماية القسمة على صفر
الموجودة في `evaluation.py` اليوم). يُحسب على مستوى الكتالوج كاملاً، لا
لكل منتج على حدة — هذا ما يجعله "دقّة عملية" مفهومة: "أخطأنا بنسبة كذا%
من إجمالي الطلب"، لا متوسط أخطاء نسبية متفرقة.

### FVA — Forecast Value Added

```
FVA(model) = Error(naive_baseline) - Error(model)
```

موجب = النموذج أضاف قيمة حقيقية فوق التنبؤ الساذج. سالب أو صفر = التعقيد
لم يشترِ شيئاً، والتوصية عندها استخدام الساذج نفسه — أرخص وأسرع. القياس
دائماً بخط أساس ثابت (Naive، لا "آخر أفضل نموذج") حتى تبقى المقارنة عادلة
عبر الزمن.

### مخزون الأمان (Safety Stock) — طلب ومهلة توريد متغيّران

```
SS = z × √(σ²_d × L + μ²_d × σ²_L)
```

حيث `z` معامل مستوى الخدمة المطلوب (1.65 لـ95%، 2.33 لـ99%)، `σ_d`
انحراف الطلب اليومي، `L` متوسط مهلة التوريد، `μ_d` متوسط الطلب اليومي،
`σ_L` انحراف مهلة التوريد. **يحتاج بيانات مهلة توريد فعلية من ملف مخزون
— لا يُقدَّر بلا ذلك.**

### نقطة إعادة الطلب (Reorder Point)

```
ROP = (μ_d × L) + SS
```

### محاذاة المستويات — Bottom-Up (الخطوة الأولى، الأبسط)

تنبؤ الفئة = مجموع تنبؤات منتجاتها مباشرة. لا تعديل إحصائي، لا مصفوفات.
كافٍ كخطوة أولى ومتّسق حسابياً بالتعريف. **MinT** (Minimum Trace،
Wickramasuriya et al. 2019) هو المعيار الأدق حين يُحتاج توزيع الخطأ
الأمثل عبر المستويات جميعاً (لأعلى ولأسفل معاً) — يُؤجَّل حتى تثبت الحاجة
الفعلية لدقّة تفوق Bottom-Up.

## مصادر البحث

### السوق والمنافسون
- [Best Demand Planning Software in 2026](https://www.mainconverter.com/list-of-demand-planning-softwares/)
- [Best SCM Software 2026: Kinaxis vs SAP IBP vs o9 vs Blue Yonder](https://www.demystifyingplm.com/best-scm-software-2026)
- [Netstock Integrations](https://www.netstock.com/integrations/)
- [Netstock vs Streamline (GMDH)](https://gmdhsoftware.com/netstock-vs-streamline/)
- [frePPLe — open source supply chain planning](https://github.com/frePPLe/frepple)
- [OSI: frePPLe + Odoo integration](https://www.opensourceintegrators.com/publications/build-supply-chain-resiliency-odoo-erp-and-frepple)

### مسابقة M5 والدروس الإحصائية
- [M5 accuracy competition: Results, findings, and conclusions (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S0169207021001874)
- [The M5 uncertainty competition (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S0169207021001722)

### المقاييس
- [WAPE: Weighted Absolute Percentage Error — Rob J Hyndman](https://robjhyndman.com/hyndsight/wape.html)
- [Forecast Accuracy Metrics: MAPE, WAPE, Bias Explained](https://www.demandplan.io/insights/forecast-accuracy-metrics)
- [Measuring forecast model accuracy — AWS](https://aws.amazon.com/blogs/machine-learning/measuring-forecast-model-accuracy-to-optimize-your-business-objectives-with-amazon-forecast/)

### Forecast Value Added
- [Forecast value added in demand planning (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S0169207024000736)
- [How To Use Forecast Value Added Analysis](https://demand-planning.com/2018/02/12/what-is-forecast-value-added-analysis/)

### محاذاة المستويات
- [Forecast reconciliation: A review — Athanasopoulos/Hyndman](https://robjhyndman.com/papers/hf_review.pdf)
- [How to Forecast Hierarchical Time Series — Towards Data Science](https://towardsdatascience.com/how-to-forecast-hierarchical-time-series-75f223f79793/)

### مخزون الأمان وMEIO
- [Reorder Point vs. Safety Stock — GAINS](https://gainsystems.com/blog/reorder-point-vs-safety-stock-balancing-inventory-in-retail/)
- [A guide to echelon inventory: multi-echelon optimization](https://www.cleverence.com/articles/for-business/echelon-inventory-4726/)

### المنتج الجديد (Cold Start)
- [New Product Demand Forecasting Without History](https://www.fygurs.com/use-cases/new-product-demand-forecasting-cold-start)
- [Generate cold start forecasts — Amazon Forecast](https://aws.amazon.com/blogs/machine-learning/generate-cold-start-forecasts-for-products-with-no-historical-data-using-amazon-forecast-now-up-to-45-more-accurate/)

### النماذج التأسيسية للسلاسل الزمنية (سياق، لا توصية فورية)
- [Benchmarking a time-series foundation model (TimeGPT)](https://www.sciencedirect.com/science/article/pii/S2666827025001847)
- [Time Series Foundation Models: Benchmarking Challenges](https://arxiv.org/html/2510.13654v1)

### الحسابات والتعاون
- [Streamlit: User authentication and information](https://docs.streamlit.io/develop/concepts/connections/authentication)
- [st.login — Streamlit Docs](https://docs.streamlit.io/develop/api-reference/user/st.login)

### مصير Amazon Forecast (سياق تنافسي)
- [AWS Lifecycle Changes](https://aws.amazon.com/products/lifecycle/)

## ملاحظة منهجية

هذه المصادر نتائج بحث ويب بتاريخ 2026-07-17، وبعضها (مثل تسعير Netstock/
GMDH الدقيق) غير منشور علناً بالكامل — أشير إلى ذلك صراحة في مكانه بدل
اختراع رقم. أي قرار تسعير أو تموضع تجاري يحتاج تحققاً مباشراً من المصدر
وقت التنفيذ، لا الاعتماد على لقطة هذا البحث وحدها.
