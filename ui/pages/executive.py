# ui/pages/executive.py
"""
الصفحة التنفيذية — "ما الذي يحتاج انتباهي؟"

تقرأ من جدولَي recommendations و forecasts، ولا تحسب شيئاً. السبب قياس:
النماذج التسعة على 185 منتجاً = 3.3 دقيقة. صفحة تحسب عند كل تحميل ميتة.
الدفعة (services/batch.py) تملأ الجداول في 0.7s بالنماذج الخفيفة.

⚠️ قرار تصميمي كشفته البيانات: ترتيب المنتجات بالخطورة وحدها يُنتج شاشة
عديمة الفائدة. أعلى 5 خطورة في هذا الكتالوج كلها توصيتها "أنتج 0" —
منتجات ميتة بتاريخ متذبذب. الخطورة عالية، والإجراء المطلوب: لا شيء.
لذا الشاشة الأساسية هي **ما يحتاج إنتاجاً** (كمية > 0) مرتّباً بالخطورة،
والمنتجات الخطرة الخاملة في قسم منفصل — موجودة، لا مختلطة بما يحتاج قراراً.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from config import DATABASE_PATH
from domain.entities import RiskLevel
from repositories.recommendation_repository import RecommendationRepository
from services.batch import run_batch

LEVEL_BADGE = {
    RiskLevel.LOW: "🟢 منخفضة",
    RiskLevel.MEDIUM: "🟡 متوسطة",
    RiskLevel.HIGH: "🔴 عالية",
}

# أقل كمية تُعتبر إجراءً. الحدّ ليس تجميلياً:
# Croston/TSB يُنتجان *معدّلاً* (0.4 وحدة/شهر مثلاً)، والتوصية بأفق شهر
# واحد تُرجع الكسر كما هو. قبول أي قيمة > 0 كان يضع "أنتج 0" في جدول
# اسمه "يحتاج قراراً" — تناقض ذاتي رآه أول تشغيل حقيقي.
# 0.5 = ما يُقرَّب إلى وحدة واحدة على الأقل. دون ذلك: لا وحدة كاملة
# متوقَّعة الشهر القادم، فلا قرار إنتاج.
MIN_ACTIONABLE_UNITS = 0.5


def _run_batch_ui(products: dict[str, list[float]], full_family: bool) -> None:
    progress = st.progress(0.0, text="جارٍ الحساب...")

    def on_progress(done: int, total: int, name: str) -> None:
        progress.progress(done / total, text=f"{done}/{total} — {name[:40]}")

    report = run_batch(products, use_fast_models=not full_family, on_progress=on_progress)
    progress.empty()

    if report.failure_count:
        st.warning(
            f"تم حساب {report.succeeded} من {report.total} في "
            f"{report.elapsed_seconds:.1f}s. فشل {report.failure_count} — "
            f"غالباً منتجات بلا مبيعات كافية."
        )
        with st.expander("تفاصيل الفشل"):
            for name, reason in report.failed[:20]:
                st.write(f"**{name}** — {reason}")
    else:
        st.success(
            f"تم حساب {report.succeeded} منتجاً في {report.elapsed_seconds:.1f}s."
        )


def _format_quantity(value: float) -> str:
    """الكميات الصغيرة بمنزلة عشرية.

    نماذج الطلب المتقطّع تُرجع معدّلات كسرية؛ round() كان يعرض 0.4 كصفر،
    فيقرأ المستخدم "أنتج 0" في جدول "يحتاج قراراً".
    """
    if value < 10:
        return f"{value:.1f}"
    return f"{value:,.0f}"


def _to_frame(recommendations) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "المنتج": r.product_name,
            "الكمية الموصى بها": _format_quantity(r.recommended_quantity),
            "الخطورة": round(r.risk.score),
            "المستوى": LEVEL_BADGE[r.risk.level],
            "تغيّر الطلب %": round(r.expected_demand_change_pct, 1),
            "ثقة التقييم": f"{r.risk.confidence:.0%}",
        }
        for r in recommendations
    ])


def render(months: list[str], products: dict[str, list[float]]) -> None:
    st.title("📊 النظرة التنفيذية")

    repository = RecommendationRepository(db_path=DATABASE_PATH)
    stored = repository.highest_risk(limit=500)

    with st.sidebar:
        st.header("الحساب")
        full_family = st.checkbox(
            "كل النماذج التسعة", value=False,
            help="أدقّ، لكن ~3.3 دقيقة على 185 منتجاً. الخفيفة: ~1 ثانية.",
        )
        if st.button("🔄 إعادة حساب الكتالوج", use_container_width=True):
            _run_batch_ui(products, full_family)
            st.rerun()

    if not stored:
        st.info(
            "لا توصيات محفوظة بعد. اضغط **إعادة حساب الكتالوج** في الشريط "
            "الجانبي — النماذج الخفيفة تُنهي الـ 185 منتجاً في نحو ثانية."
        )
        return

    actionable = [
        r for r in stored if r.recommended_quantity >= MIN_ACTIONABLE_UNITS
    ]
    idle = [r for r in stored if r.recommended_quantity < MIN_ACTIONABLE_UNITS]
    dormant_risky = [r for r in idle if r.risk.level == RiskLevel.HIGH]
    high_risk_actionable = [r for r in actionable if r.risk.level == RiskLevel.HIGH]

    columns = st.columns(4)
    columns[0].metric("منتجات مُقيَّمة", len(stored))
    columns[1].metric("تحتاج إنتاجاً", len(actionable))
    columns[2].metric("منها عالية الخطورة", len(high_risk_actionable))
    columns[3].metric(
        "إجمالي الكمية الموصى بها",
        f"{sum(r.recommended_quantity for r in actionable):,.0f}",
    )

    st.subheader("يحتاج قراراً — مرتّب بالخطورة")
    st.caption(
        "المنتجات التي يوصى بإنتاج كمية منها. الخطورة تحدد الأولوية، "
        "لا الحاجة نفسها."
    )
    if actionable:
        st.dataframe(
            _to_frame(actionable[:50]), use_container_width=True, hide_index=True
        )
    else:
        st.info("لا منتج يحتاج إنتاجاً حسب التوصيات الحالية.")

    if dormant_risky:
        with st.expander(f"⏸️ خامل لكن عالي الخطورة ({len(dormant_risky)})"):
            st.caption(
                f"أقل من {MIN_ACTIONABLE_UNITS} وحدة متوقَّعة الشهر القادم — "
                "لا قرار إنتاج. خطورتها عالية بسبب تاريخ متذبذب: معلومة "
                "تستحق النظر (منتج يموت؟) لا إجراءً. فُصلت كي لا تزاحم ما "
                "يحتاج قراراً فعلياً."
            )
            st.dataframe(
                _to_frame(dormant_risky[:30]), use_container_width=True, hide_index=True
            )

    st.caption(
        "⚠️ عامل نفاد المخزون غير محسوب — جدول inventory فارغ حتى Phase 5. "
        "لذا ثقة التقييم 80% (4 عوامل من 5) لكل المنتجات."
    )
