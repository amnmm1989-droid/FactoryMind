# services/reconciliation.py
"""
Bottom-Up: إجمالي كل فئة = مجموع توصيات منتجاتها — لا محسوباً بمعزل ثم
يُتحقّق من اتساقه.

هذا هو الفارق الجوهري عن الأساليب الأدقّ (MinT) التي تحسب تنبؤاً لكل
مستوى (منتج، فئة، إجمالي) بمعزل ثم تُصالح بينها إحصائياً. Bottom-Up أبسط
جذرياً: لا تنبؤ مستقل للفئة إطلاقاً — رقمها *مُعرَّف* بالجمع. النتيجة
متّسقة حسابياً بالتعريف، لا "غالباً" ولا "بعد تسوية". يُترقّى إلى MinT
حين يثبت أن الدقة الإضافية تستحق التعقيد — لا قبل ذلك (نفس مبدأ المشروع
في كل مكان آخر: لا تشترِ تعقيداً بلا دليل على فائدته).

فئة غير معروفة لمنتج (`category_of` لا يحمله) تُستبعد من كل الإجماليات —
لا تُحتسب في فئة "أخرى" مخترعة. نفس مبدأ None ≠ 0 في risk_service: مجهول
لا يُقاس، لا يُصفَّر.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from domain.entities import ProductionRecommendation


@dataclass(frozen=True)
class CategoryTotal:
    """إجمالي فئة واحدة — الكمية والعدد الذي بُنيت منه."""

    category: str
    total_quantity: float
    product_count: int


def category_totals(
    category_of: dict[str, str],
    recommendations: Sequence[ProductionRecommendation],
) -> list[CategoryTotal]:
    """إجمالي كل فئة، مرتّباً تنازلياً بالكمية.

    الجمع نفسه هو كل المنطق: recommended_quantity لكل منتج معروف الفئة
    يُضاف إلى إجمالي فئته. لا وزن، لا تعديل، لا تقريب — الاتساق الحسابي
    مضمون لأن لا حساب مستقل يمكن أن ينحرف عنه.
    """
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}

    for recommendation in recommendations:
        category = category_of.get(recommendation.product_name)
        if category is None:
            continue
        totals[category] = totals.get(category, 0.0) + recommendation.recommended_quantity
        counts[category] = counts.get(category, 0) + 1

    return sorted(
        (
            CategoryTotal(category=category, total_quantity=quantity,
                          product_count=counts[category])
            for category, quantity in totals.items()
        ),
        key=lambda c: c.total_quantity,
        reverse=True,
    )
