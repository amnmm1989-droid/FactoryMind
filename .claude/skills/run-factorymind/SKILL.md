---
name: run-factorymind
description: Build, run, and drive FactoryMind — a Streamlit demand-forecasting app. Use when asked to start or launch FactoryMind, run its tests, take a screenshot of its dashboard, verify a change to the forecast/risk/decision engines, or interact with the running app.
---

FactoryMind هو نظام تحليل وتنبؤ أوامر التصنيع: تطبيق Streamlit (Python)
يُصيَّر في المتصفح. مقبضان لا واحد:

- **`.claude/skills/run-factorymind/smoke.py`** — يشغّل المحرّكات مباشرةً
  بلا واجهة. **ابدأ من هنا**: `services/` عُدِّل 22 مرة عبر تاريخ المشروع
  بينما `ui/` لم يُلمس منذ Phase 1، ومحرّكات التنبؤ/الخطورة/القرار
  **غير موصولة بالواجهة أصلاً**. تغييرك فيها لن يظهر في أي لقطة شاشة.
- **`.claude/skills/run-factorymind/driver.mjs`** — يُشغّل Streamlit
  ويقوده بـ Playwright. للواجهة فقط.

كل المسارات أدناه نسبةً إلى جذر المستودع.

## Prerequisites

لا شيء عبر `apt-get`. Python 3.14 و Node v22 كانا موجودين؛ متصفح
Playwright مخزّن مسبقاً في `~/.cache/ms-playwright`.

## Build

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.lock.txt   # الإصدارات المُختبَرة (69 حزمة، ~4 دقائق، 1.5GB)
./.venv/bin/python migrate.py                      # إلزامي — انظر Gotchas
```

للـ driver فقط (مرة واحدة، ولا يمسّ اعتمادات المشروع):

```bash
cd .claude/skills/run-factorymind && npm install && cd -
```

## Run (agent path) — المحرّكات، بلا واجهة

```bash
./.venv/bin/python .claude/skills/run-factorymind/smoke.py --fast
```

يفحص الـ schema، يشغّل محرك التنبؤ ثم محرك القرار، ويطبع ترتيب النماذج
والتوصية. يخرج بـ 1 عند أول فشل. **`--fast` يستغرق 0.0s** ويقتصر على
النماذج الخفيفة (Naive/MovingAverage/Croston/TSB)؛ بدونه ~10s لأن
Prophet و XGBoost يُدرَّبان فعلاً.

```bash
# كل النماذج التسعة على منتج بعينه
./.venv/bin/python .claude/skills/run-factorymind/smoke.py --product "Rwanda" --steps 3
```

مخرجات حقيقية (`--fast`):

```
✓ الـ schema كاملة (/home/abdulrahman/Claude/FactoryMind/data/app.db)

▸ المنتج: Hydraulic Pump 50mm
  نقاط: 44 | غير صفرية: 44 | تصنيف: smooth (ADI=1.00)
  المقياس: rmse | الفائز: TSB
  النموذج             RMSE (*)       تراكمي
  TSB                    62.85         34.0
  Croston                64.51         93.8
  MovingAverage          66.29        131.0
  Naive                 110.31        545.0

  يوصى بإنتاج 201 وحدة ... بسبب ارتفاع الطلب المتوقع بنسبة 4.8%
  خطورة: 35/100 (medium) | ثقة: 80% | مجهول: 1
✓ فحوص السلامة نجحت
```

العمود المعلَّم `(*)` هو المقياس الذي رُتِّب به — يتبدّل إلى `تراكمي` على
السلاسل المتقطّعة (84% من الكتالوج). راجع `docs/ROADMAP.md`.

### استدعاء مباشر

المحرّكات نقية ولا تحتاج قاعدة بيانات للتنبؤ:

```bash
./.venv/bin/python -c "
import warnings, json, logging; warnings.filterwarnings('ignore'); logging.disable(logging.INFO)
from services.forecast_engine import forecast_product, classify_demand
data = json.load(open('data/data.json'))
name, series = next(iter(data['products'].items()))
print(classify_demand(series).demand_class.value)
print(forecast_product(name, series, steps=3, use_cache=False).best_model_name)
"
```

`logging.disable(logging.INFO)` ضروري — بدونه يُغرق cmdstanpy المخرجات.

## Run (agent path) — الواجهة

```bash
node .claude/skills/run-factorymind/driver.mjs shot   # لقطة
node .claude/skills/run-factorymind/driver.mjs text   # قراءة الـ DOM المُصيَّر
node .claude/skills/run-factorymind/driver.mjs flow   # تدفق: تمديد أفق التنبؤ
```

كل أمر يُشغّل الخادم على المنفذ 8701، ينتظره، يقود المتصفح، ثم ينظّف.
الدورة ~25s (إقلاع Streamlit ~12s). اللقطات تُحفظ في
`.claude/skills/run-factorymind/screenshots/`.

`text` يطبع العنوان وأول 6 مؤشرات وعدد رسوم Plotly المُصيَّرة — الحكم
الوحيد الصادق على أن التطبيق يعمل (انظر Gotchas).

`flow` يمدّد أفق التنبؤ 6 → 12 ويلتقط `flow-before.png` و`flow-after.png`.
يفشل صراحةً لو لم يتحرّك الشريط.

لمنفذ آخر: `PORT=8899 node .claude/skills/run-factorymind/driver.mjs shot`

## Run (human path)

```bash
./.venv/bin/streamlit run app.py     # http://localhost:8501
```

يحاول فتح متصفح؛ بلا فائدة headless — استخدم الـ driver.

## Test

```bash
./.venv/bin/python -m pytest -q      # 219 اختباراً، ~1:40 دقيقة
```

بطيء لأن الاختبارات تُدرّب نماذج حقيقية. للدورة السريعة (49 اختباراً،
migrations + الخطورة — لا نماذج):

```bash
./.venv/bin/python -m pytest tests/test_migrations.py tests/test_risk_service.py -q   # ~0.5s
```

## Gotchas

- **`python migrate.py` إلزامي قبل أول تشغيل.** الـ schema مملوكة لـ
  `migrations/*.sql`؛ المستودع يتحقق ولا يُنشئ. تخطّيها يعطي
  `MigrationError: قاعدة البيانات ناقصة 9 جدول`. آمن للتكرار.

- **`curl` عديم الفائدة للحكم على الواجهة.** Streamlit يردّ HTTP 200
  بهيكل فارغ ثم يُصيّر عبر JavaScript — تحصل على 200 حتى لو كان التطبيق
  يعرض خطأً. الشاهد الوحيد هو `driver.mjs text` (ينتظر
  `[data-testid="stMetric"]`).

- **شريط Streamlit ليس `[role="slider"]`.** النمط الشائع في Playwright
  لا ينطبق: فحص الـ DOM يعطي `role=slider: 0` مقابل
  `input[type=range]: 1`. استخدم
  `[data-testid="stSlider"] input[type="range"]`.

- **`click()` على الشريط ينتهي مهلته بعد 30s** رغم أن الـ input مرئي
  (129×16، opacity=1) — Streamlit يضع مقبضاً مخصّصاً فوقه يعترض أحداث
  المؤشر. استخدم `focus()` ثم أسهم لوحة المفاتيح. و`fill()` ليس بديلاً:
  ضبط القيمة برمجياً لا يُطلق دورة إعادة تشغيل Streamlit.

- **افصل الضغطات بـ ~300ms.** كل ضغطة تُطلق rerun؛ التتابع السريع يُسقط
  بعضها ويصل الشريط إلى قيمة أقل من المتوقّع.

- **تمديد الأفق لا يغيّر "قيمة التنبؤ (أول شهر)".** صحيح لا عطل — تنبؤ
  الشهر الأول مستقل عن طول الأفق. الأثر المرئي هو اتساع نطاق التنبؤ في
  الرسم.

- **Streamlit يُغرق stderr** بتحذيرات إهمال (`use_container_width`).
  `driver.mjs` يجمّع السجل ويطبعه عند الفشل فقط، والخطأ يُطبع **بعده**
  ليبقى مرئياً تحت `| tail`.

- **`--fast` يبدّل النموذج الفائز.** يستبعد Prophet/XGBoost/RF، فالنتيجة
  ليست ما سيختاره المحرك في الإنتاج. للتحقق النهائي شغّله بلا `--fast`.

- **البيئة 1.5GB** — معظمها `nvidia-nccl-cu12` (~200MB) يجرّه XGBoost
  حتى على جهاز بلا GPU.

## Troubleshooting

| العرض | السبب والحل |
|---|---|
| `MigrationError: قاعدة البيانات ناقصة 9 جدول` | لم تُشغَّل الـ migrations. `./.venv/bin/python migrate.py` |
| `ModuleNotFoundError: No module named 'pandas'` | تُشغّل python النظام لا الـ venv. استخدم `./.venv/bin/python` |
| `ERR_MODULE_NOT_FOUND: playwright` | `cd .claude/skills/run-factorymind && npm install` |
| `elementHandle.click: Timeout 30000ms exceeded` | مقبض Streamlit يعترض المؤشر. `focus()` + أسهم |
| `الخادم لم يستجب على http://localhost:8701` | منفذ عالق من تشغيل سابق. `pkill -f "streamlit run app.py"` |
| مخرجات الـ driver تبدو تحذيرات Streamlit فقط | الخطأ في آخر سطر. `2>&1 \| grep -E "^(✓\|✗)"` |
| `الـ migration رقم NNN تغيّر بعد تطبيقه` | عُدِّل ملف SQL مُطبَّق. أنشئ migration جديداً بدل تعديله |
