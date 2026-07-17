# core/runtime_mode.py
"""
وضع التشغيل: مستضاف أم محلي.

المشروع يخدم هدفين لا يتعارضان:

    محلي  — تستنسخه وتشغّله على جهازك. بياناتك تُحفَظ في data/app.db،
            وتبقى بين الجلسات، والصفحة التنفيذية تقرأ منها.

    مستضاف — موقع عام يفتحه أي أحد بنقرة. **لا حفظ إطلاقاً**: بيانات كل
            زائر تعيش في جلسته وتموت معها.

لماذا لا حفظ في المستضاف؟ ليس تكاسلاً بل ضرورتان:

1. **الخصوصية.** نسخة واحدة تخدم كل الزوّار، و`data/app.db` ملف واحد
   مشترك. أول زائر يرفع مبيعاته يكتبها في جدول products؛ الثاني يفتح
   الصفحة فيراها. بيانات مبيعات المصانع سرّ تجاري — والتسريب هنا ليس
   احتمالاً بل حتمية معمارية.

2. **إنه ممكن أصلاً.** النماذج الخفيفة تُنهي كتالوجاً كاملاً في أقل من ثانية،
   فلا حاجة لتخزين نتيجة تُحسب أسرع من قراءتها. لولا أن الساذج يفوز على
   هذه البيانات (راجع docs/ROADMAP.md) لاحتاج كل زائر 3.3 دقيقة ولاستحال
   الوضع المستضاف من أساسه.

التفعيل:
    FACTORYMIND_MODE=hosted streamlit run app.py
"""
from __future__ import annotations

import os
from enum import Enum

ENV_VAR = "FACTORYMIND_MODE"


class RuntimeMode(str, Enum):
    LOCAL = "local"
    HOSTED = "hosted"

    @property
    def persists(self) -> bool:
        """هل يُسمح بالكتابة في قاعدة البيانات؟"""
        return self is RuntimeMode.LOCAL

    @property
    def bundles_demo_data(self) -> bool:
        """هل تُعرض بيانات العرض المرفقة حين لا يرفع المستخدم شيئاً؟

        نعم في الوضعين — لكن معناها يختلف: محلياً هي بياناتك الافتراضية،
        ومستضافاً هي مجرد عيّنة ليرى الزائر الأداة قبل أن يرفع ملفه.
        """
        return True


def current_mode() -> RuntimeMode:
    """الوضع من متغيّر البيئة. الافتراضي محلي — الأقل مفاجأة لمن يستنسخ."""
    raw = os.environ.get(ENV_VAR, "").strip().lower()
    if raw == RuntimeMode.HOSTED.value:
        return RuntimeMode.HOSTED
    return RuntimeMode.LOCAL


def is_hosted() -> bool:
    return current_mode() is RuntimeMode.HOSTED
