# 🔮 نظام تحليل وتنبؤ أوامر التصنيع – الإصدار الاحترافي

نظام تحليل وتنبؤ متقدم باستخدام Streamlit و Python، مصمم لتحليل بيانات أوامر التصنيع والتنبؤ بالطلب المستقبلي باستخدام نماذج إحصائية متطورة.

---

## 🚀 التشغيل

```bash
# 1. البيئة
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock.txt      # الإصدارات المُختبَرة بالضبط

# 2. قاعدة البيانات (مرة واحدة — آمن للتكرار)
python migrate.py

# 3. التطبيق
streamlit run app.py
```

الخطوة 2 إلزامية: بنية القاعدة مملوكة لـ `migrations/`، والتطبيق يتحقق
منها ولا ينشئها. تخطّيها يعطي رسالة واضحة تطلب تشغيلها.

```bash
python migrate.py --status    # ما هو مطبَّق وما هو معلّق
pytest                        # 48 اختباراً
```

---

## 📁 هيكل المشروع

```
app.py                 نقطة الدخول (composition root)
config.py              الإعدادات القديمة (لا تزال مستخدمة)
migrate.py             مشغّل الـ migrations — idempotent وذرّي

core/                  الأساس (Phase 0): إعدادات، logging، استثناءات
domain/entities.py     كائنات Domain نقية — العقد بين الطبقات
migrations/            NNN_*.sql — المالك الوحيد لبنية قاعدة البيانات
repositories/          طبقة الوصول للبيانات (JSON | SQLite عبر factory)
services/              منطق الأعمال (Phase 1)
models/                النماذج الإحصائية: ETS، SARIMA، الاتجاه، الشذوذ
ui/                    واجهات Streamlit
data/                  data.json (المصدر) + app.db (مُولَّدة، غير مُتتبَّعة)
docs/                  ARCHITECTURE، ROADMAP، أدلة المراحل
tests/                 pytest
```

راجع [`docs/ROADMAP.md`](docs/ROADMAP.md) لخطة التطوير،
و[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) للمعمارية.
