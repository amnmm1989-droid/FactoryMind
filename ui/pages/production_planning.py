# ui/pages/production_planning.py
"""
تخطيط الإنتاج — تحويل توصية النظام إلى قرار إنسان.

الفصل بين الجدولين متعمّد منذ Phase 2:
    recommendations   = اقتراح النظام
    production_plans  = ما قرّره المخطِّط فعلاً
قد يوافق أو يخالف. الفصل يسمح بقياس: كم مرة تُتَّبع التوصيات؟

وهو وعدٌ لم يكن يُنفَّذ: كانت هذه الصفحة تكتب SQL الخطط بنفسها — وحدها
بين الصفحات الخمس — وتُغفل source_recommendation_id، فيبقى NULL أبداً
ويصير السؤال بلا جواب رغم أن الجدول بُني لأجله. الآن يملك
ProductionPlanRepository الاستعلامات، ويكتب الرابط، ويُجيب عبر adherence().

⚠️ حدّ باقٍ: "هل النتائج أفضل حين تُتَّبع؟" يحتاج actual_quantity — يُملأ
بعد التنفيذ الفعلي، ولا شيء يملؤه بعد (بند الإنتاج الفعلي في الخارطة).

⚠️ حدّ معروف: الكميات هنا لا تخصم المخزون، لأن جدول inventory فارغ حتى
Phase 5. محرك القرار يخصم المخزون المتاح حين يُمرَّر إليه — ولا شيء
يُمرَّر بعد. المعروض هو الطلب المتوقَّع كاملاً.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.logging_config import get_logger
from core.runtime_mode import is_hosted
from repositories.production_plan_repository import (
    STATUS_CODES,
    ProductionPlanRepository,
)
from repositories.recommendation_repository import RecommendationRepository
from ui.data_source import active_dataset
from ui.i18n import format_month, format_reason, t

logger = get_logger(__name__)


def _status_label(code: str) -> str:
    return t(f"status.{code}")


def _adherence_summary_params(stats: dict[str, int]) -> dict[str, float | int] | None:
    """حساب بلا عرض — قابل للاختبار بمعزل عن Streamlit.

    None يعني: لا خطة يمكن الحكم عليها بعد (كل الخطط بلا توصية مرتبطة، أو
    لا خطط أصلاً). النسبة على judged = total - unlinked لا على total: خطة
    بلا توصية مرتبطة لا يمكن الحكم عليها متابعةً أو مخالفةً أصلاً، فقسمتها
    على الإجمالي تُصغِّر النسبة كذباً — نفس مبدأ adherence() نفسه.
    """
    judged = stats["total"] - stats["unlinked"]
    if judged <= 0:
        return None
    return {
        "judged": judged,
        "followed": stats["followed"],
        "overridden": stats["overridden"],
        "unlinked": stats["unlinked"],
        "pct": stats["followed"] / judged * 100,
    }


def _render_adherence(stats: dict[str, int]) -> None:
    """"كم مرة تُتَّبع توصياتنا؟" — السؤال الذي بُني الجدول لأجله في 007،
    وصار قابلاً للإجابة بعد أن صار source_recommendation_id يُكتب فعلاً.
    """
    params = _adherence_summary_params(stats)
    if params is None:
        st.caption(t("plan.adherence_none"))
        return

    st.subheader(t("plan.adherence_title"))
    st.caption(t("plan.adherence_summary", **params))


def _plans_frame(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["status"] = frame["status"].map(_status_label)
    frame["month"] = frame["month"].map(format_month)
    return frame.rename(columns={
        "product": t("common.product"), "month": t("common.month"),
        "planned_quantity": t("plan.planned"), "actual_quantity": t("plan.actual"),
        "status": t("plan.status"), "notes": t("plan.notes_column"),
        "updated_at": t("plan.updated"),
    })


def render(months: list[str], products: dict[str, list[float]]) -> None:
    st.title(t("plan.title"))
    st.caption(t("plan.subtitle"))

    # الخطط تُكتب في production_plans، ومفتاحها الأجنبي يشير إلى جدول
    # products — الذي يحمل بيانات العرض لا ملف المستخدم. حفظ خطة لمنتج
    # مرفوع سيفشل بـ DataAccessError. الرفض هنا صريح ومُفسَّر بدل انهيار
    # عند الضغط على "حفظ".
    _, _, is_user_data = active_dataset()
    if is_user_data or is_hosted():
        reason = t("plan.reason_user_data" if is_user_data else "plan.reason_hosted")
        st.info(t("plan.local_only", reason=reason), icon="ℹ️")
        # تعليمات يتبعها زائر فعلاً، فتُختبَر لا تُكتب من الذاكرة:
        # كانت تقول `python migrate.py` — لم تعد لازمة بعد أن صار الإقلاع
        # يبني القاعدة — وتُغفل تثبيت الاعتماديات، فالاستنساخ يفشل بلا
        # streamlit أصلاً. سطرٌ ناقص هنا يعني زائراً عالقاً في طرفيته.
        st.code(
            "git clone https://github.com/amnmm1989-droid/FactoryMind\n"
            "cd FactoryMind\n"
            "pip install -r requirements.lock.txt\n"
            "streamlit run app.py",
            language="bash",
        )
        st.caption(t("plan.local_only_note"))
        return

    st.warning(t("plan.inventory_warning"), icon="⚠️")

    recommendations = RecommendationRepository()
    plans = ProductionPlanRepository()
    month_options = plans.month_options()

    st.subheader(t("plan.create"))
    with st.form("new_plan"):
        columns = st.columns([3, 2])
        product = columns[0].selectbox(t("common.product"), sorted(products))
        month_label = columns[1].selectbox(
            t("common.month"), [name for _, name in month_options],
            format_func=format_month,
        )

        # المعرّف لا الكيان وحده: هو ما يُكتب في source_recommendation_id
        # فيُسجَّل أي توصية رآها المخطِّط ساعة قراره.
        found = recommendations.latest_with_id_for_product(product)
        recommendation_id, recommendation = found if found else (None, None)
        suggested = round(recommendation.recommended_quantity) if recommendation else 0
        if recommendation:
            st.caption(t("plan.system_suggests", quantity=suggested,
                         reason=format_reason(recommendation)))
        else:
            st.caption(t("plan.no_recommendation"))

        columns = st.columns([2, 2, 4])
        quantity = columns[0].number_input(
            t("plan.planned_qty"), min_value=0.0, value=float(suggested), step=10.0
        )
        status = columns[1].selectbox(
            t("plan.status"), STATUS_CODES, format_func=_status_label
        )
        notes = columns[2].text_input(t("plan.notes"))

        if st.form_submit_button(t("plan.save"), use_container_width=True):
            month_id = next(mid for mid, name in month_options if name == month_label)
            plans.save(product, month_id, quantity, status, notes,
                       source_recommendation_id=recommendation_id)
            if recommendation and quantity != suggested:
                st.info(t("plan.overridden", suggested=suggested, actual=quantity))
            st.success(t("plan.saved", product=product[:40],
                         month=format_month(month_label)))

    _render_adherence(plans.adherence())

    st.subheader(t("plan.existing"))
    frame = _plans_frame(plans.all_plans())
    if frame.empty:
        st.info(t("plan.none_yet"))
    else:
        st.dataframe(frame, use_container_width=True, hide_index=True)
