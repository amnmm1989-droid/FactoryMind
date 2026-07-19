# services/provenance.py
"""
سجلّ التدقيق — «على أي أساسٍ بُني هذا الملف، ومتى، وبأي بيانات؟»

## المشكلة التي يحلّها

ملف Excel الذي تُصدّره خطة الشراء يُرسَل بالبريد ويُبنى عليه أمر شراء
بمئات الآلاف. وكان يخرج بلا **تاريخ**، ولا اسم ملف مصدر، ولا ذكرٍ
للنماذج المستخدَمة، ولا للدقّة المقيسة، ولا للتحذيرات التي رآها من
صدّره. أي أنه رقمٌ بلا نسب.

أربع حالات تقع فعلاً ويحسمها هذا السجلّ:

1. **«أداتكم قالت أنتجوا 5,000 فعلقنا بالمخزون.»** — الجولة موثّقة
   ببصمة بياناتها وبالدقّة التي عُرضت وقتها.
2. **«أي ملف بُني عليه هذا؟»** — أكثرها وقوعاً. معظم النزاعات حول
   *البيانات* لا حول النموذج: تصديرة صُحّحت ونُسي إعادة الحساب.
   البصمة تحسمها في ثوانٍ.
3. **خطة عمرها ثلاثة أشهر تُنفَّذ اليوم** — لأن الملف لم يحمل تاريخاً.
4. **مخطّط المشتريات يبرّر أمر شراء لمدقّق الجودة.** وهذه أهمّها
   تجارياً: بلا سجلّ جوابه «البرنامج قال» — وهو جواب يُضعف موقفه، فيتردّد
   في استعمال الأداة في القرارات الكبيرة، وهي التي تبرّر ثمنها.

## ما لا يفعله — بصراحة

**لا يحمي من تنبؤ خاطئ.** لا يجعل الرقم أصحّ. يحسم فقط النزاع حول *ما
الذي حدث فعلاً*، وهو أغلب ما يقع.

## لماذا نصّ لا كائن

المخرَج أزواج (مفتاح ترجمة، قيمة) بترتيب ثابت — لتُصيَّر ورقةَ Excel
مباشرةً. القيم مُصاغة هنا لأن هذا السجلّ يُقرأ خارج الأداة، حيث لا
تنسيق ولا لغة واجهة.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence


def fingerprint(products: dict[str, Sequence[float]]) -> str:
    """بصمة قصيرة للبيانات — تتغيّر بتغيّر الأرقام لا الأسماء فقط.

    اثنا عشر خانة تكفي: الغرض تمييز تصديرة عن أخرى في نزاع، لا الحماية
    من تزوير متعمَّد. بصمة أطول تملأ الخلية ولا تُقرأ.
    """
    digest = hashlib.sha256()
    for name in sorted(products):
        digest.update(name.encode("utf-8"))
        digest.update(b"|")
        digest.update(",".join(f"{v:.4f}" for v in products[name]).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()[:12]


# مفاتيح صريحة لا f-string: مفتاح مبنيّ ديناميكياً يفلت من حارس المفاتيح
# اليتيمة (tests/test_i18n.py)، فيتعفّن نصٌّ حيّ بصمت. نفس علاج
# executive._render_sort_control.
_SCOPE_KEYS = {
    "fast": "audit.scope.fast",
    "full": "audit.scope.full",
    "custom": "audit.scope.custom",
}


@dataclass(frozen=True)
class RunProvenance:
    """كل ما يلزم لإعادة بناء جولة والحكم عليها لاحقاً."""

    products: dict[str, Sequence[float]]
    granularity: str
    period_count: int
    period_range: tuple[str, str] | None = None
    source_name: str | None = None
    model_scope: str = "fast"          # "fast" | "full" | "custom"
    model_names: Sequence[str] = ()
    horizon: int | None = None
    lead_time_days: int | None = None
    warning_codes: Sequence[str] = ()
    measured_share: float | None = None    # نسبة ما قِيست دقّته
    median_wape: float | None = None
    beat_naive_share: float | None = None
    inventory_used: bool = False
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def rows(self) -> list[tuple[str, str]]:
        """أزواج (مفتاح ترجمة، قيمة) بترتيب ثابت.

        ⚠️ الترتيب ليس تجميلياً: من يفتح الورقة في نزاع يبحث أولاً عن
        «متى؟» و«أي ملف؟». فيُقدَّمان.
        """
        unknown = "—"
        rows: list[tuple[str, str]] = [
            ("audit.generated_at",
             self.generated_at.strftime("%Y-%m-%d %H:%M UTC")),
            ("audit.source", self.source_name or unknown),
            ("audit.fingerprint", fingerprint(self.products)),
            ("audit.granularity", self.granularity),
            ("audit.periods", str(self.period_count)),
        ]
        if self.period_range:
            rows.append(("audit.range", f"{self.period_range[0]} → {self.period_range[1]}"))
        rows.append(("audit.products", str(len(self.products))))

        rows.append(("audit.model_scope", _SCOPE_KEYS[self.model_scope]))
        if self.model_names:
            rows.append(("audit.models", "، ".join(self.model_names)))
        if self.horizon is not None:
            rows.append(("audit.horizon", str(self.horizon)))
        if self.lead_time_days:
            rows.append(("audit.lead_time", str(self.lead_time_days)))

        rows.append(("audit.inventory",
                     "audit.yes" if self.inventory_used else "audit.no"))

        # الدقّة: تُذكَر حين قِيست فقط. "—" هنا يعني «لم يُشغَّل التحقّق»،
        # لا «الدقّة صفر» — والفرق هو كل شيء في نزاع.
        rows.append((
            "audit.measured_share",
            f"{self.measured_share:.0%}" if self.measured_share is not None else unknown,
        ))
        rows.append((
            "audit.median_wape",
            f"{self.median_wape:.0f}%" if self.median_wape is not None else unknown,
        ))
        rows.append((
            "audit.beat_naive",
            f"{self.beat_naive_share:.0%}" if self.beat_naive_share is not None else unknown,
        ))

        # التحذيرات التي رآها من صدّر الملف — لا تُطوى بعد إغلاق الشاشة.
        rows.append((
            "audit.warnings",
            "، ".join(self.warning_codes) if self.warning_codes else "audit.none",
        ))
        # ما يُثبته السجلّ وما لا يُثبته — داخل الورقة لا في وثيقة منفصلة.
        # من يفتح هذا الملف في نزاع لن يقرأ دليلاً، وادّعاءٌ ضمنيّ بأن
        # الورقة "تُثبت صحّة التنبؤ" أسوأ من غيابها.
        rows.append(("audit.note", "audit.note_body"))
        return rows
