# services/decision_engine/__init__.py
"""
محرك القرار (Phase 4): تنبؤ -> توصية إنتاج.

    from services.decision_engine import recommend_production

    rec = recommend_production("منتج", series, forecast, inventory=None)
    rec.recommended_quantity   # الكمية بعد خصم المخزون المتاح
    rec.as_message()           # "يوصى بإنتاج 240 وحدة من المنتج ..."
    rec.reason                 # الأساس الكامل — النموذج، خطؤه، الخطورة
    rec.risk.level             # LOW / MEDIUM / HIGH

التوصية تحمل خطورتها ومصدرها معها. لا رقم بلا سياق.
"""
from .purchase_plan import PurchaseOrderLine, PurchasePlan, build_purchase_plan
from .recommender import BASELINE_MONTHS, borrow_recommendation, recommend_production

__all__ = [
    "recommend_production", "borrow_recommendation", "BASELINE_MONTHS",
    "build_purchase_plan", "PurchasePlan", "PurchaseOrderLine",
]
