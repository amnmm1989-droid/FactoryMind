# ui/pages/product_intelligence.py
"""
ذكاء المنتج — لماذا يتصرّف هذا المنتج هكذا.

تجيب الأسئلة التي لا تجيبها لوحة الأرقام: لماذا رُفض SARIMA على هذا
المنتج؟ لماذا خطورته 47؟ أي نموذج فاز آخر مرة ولماذا؟

تعرض ما تعمّدنا عدم إخفائه: العوامل غير المحسوبة، وثقة التقييم، وتصنيف
الطلب الذي يحدد أي عائلة نماذج تنطبق أصلاً.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import DATABASE_PATH
from core.exceptions import AppError
from core.runtime_mode import is_hosted
from domain.entities import RiskLevel
from repositories.forecast_repository import ForecastRepository
from repositories.recommendation_repository import RecommendationRepository
from services.batch import fast_models
from ui.data_source import active_dataset
from services.forecast_engine import classify_demand, forecast_product
from services.risk_service import FACTOR_WEIGHTS, compute_risk

CLASS_INFO = {
    "smooth": ("منتظم", "طلب كل شهر بأحجام متماسكة — العائلة الموسمية في مجالها."),
    "erratic": ("متذبذب", "يحدث غالباً، لكن بأحجام شديدة التقلب."),
    "intermittent": ("متقطّع", "فجوات كثيرة، أحجام متماسكة — مجال Croston/TSB."),
    "lumpy": ("متكتّل", "فجوات *و* تقلب — الأصعب على كل النماذج."),
    "dead": ("بلا مبيعات", "لا طلب قط — لا نموذج ينطبق."),
}

FACTOR_LABELS = {
    "demand_volatility": "تقلب الطلب",
    "stock_depletion_risk": "نفاد المخزون",
    "forecast_accuracy_penalty": "عدم دقة التنبؤ",
    "seasonality_factor": "الموسمية",
    "growth_rate": "معدّل التغيّر",
}


def _risk_chart(risk) -> go.Figure:
    """العوامل المعروفة فقط — المجهول لا يُرسم كصفر."""
    known = risk.known_factors
    labels = [FACTOR_LABELS[name] for name in known]
    values = list(known.values())
    colors = ["#d62728" if v >= 70 else "#ff7f0e" if v >= 30 else "#2ca02c"
              for v in values]

    figure = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=colors, text=[f"{v:.0f}" for v in values],
        textposition="outside",
    ))
    figure.update_layout(
        title="مساهمة كل عامل (0-100)", xaxis_range=[0, 110],
        height=280, margin=dict(t=40, b=20, l=10, r=10),
    )
    return figure


def render(months: list[str], products: dict[str, list[float]]) -> None:
    st.title("🧠 ذكاء المنتج")

    with st.sidebar:
        product = st.selectbox("المنتج", sorted(products))

    series = products[product]
    profile = classify_demand(series)
    label, explanation = CLASS_INFO.get(
        profile.demand_class.value, (profile.demand_class.value, "")
    )

    st.subheader("تصنيف الطلب")
    columns = st.columns(4)
    columns[0].metric("التصنيف", label)
    columns[1].metric("ADI", f"{profile.adi:.2f}",
                      help="متوسط الفترة بين الطلبات. 1.0 = كل شهر.")
    columns[2].metric("CV²", f"{profile.cv_squared:.2f}",
                      help="تقلب أحجام الطلب غير الصفري.")
    columns[3].metric("أشهر بمبيعات", f"{profile.non_zero_count}/{len(series)}")
    st.caption(explanation)

    if profile.demand_class.value == "dead":
        st.warning("لا مبيعات لهذا المنتج قط — لا تنبؤ ولا خطورة.")
        return

    st.plotly_chart(
        go.Figure(go.Scatter(
            x=months[-len(series):], y=series, mode="lines+markers",
            line=dict(color="#1f77b4"),
        )).update_layout(
            title="تاريخ الطلب", height=260, margin=dict(t=40, b=30),
            xaxis_title="", yaxis_title="الكمية",
        ),
        use_container_width=True,
    )

    try:
        with st.spinner("حساب الخطورة..."):
            result = forecast_product(product, series, steps=6, models=fast_models())
            risk = compute_risk(product, series, result.best)
    except AppError as exc:
        st.error(f"تعذّر التحليل: {exc.message}")
        return

    st.subheader("تفكيك الخطورة")
    columns = st.columns([1, 2])
    with columns[0]:
        badge = {RiskLevel.LOW: "🟢", RiskLevel.MEDIUM: "🟡", RiskLevel.HIGH: "🔴"}
        st.metric("الدرجة", f"{risk.score:.0f}/100",
                  delta=f"{badge[risk.level]} {risk.level.value}", delta_color="off")
        st.metric("ثقة التقييم", f"{risk.confidence:.0%}",
                  help="نسبة العوامل التي أمكن حسابها.")
    with columns[1]:
        st.plotly_chart(_risk_chart(risk), use_container_width=True)

    if risk.missing_factors:
        st.info(
            "**عوامل غير محسوبة:** "
            + "، ".join(FACTOR_LABELS[name] for name in risk.missing_factors)
            + ". استُبعدت من الحساب وأُعيدت موازنة الباقي — لم تُعامَل كصفر. "
            "الصفر يعني *قِسنا ولا خطورة*؛ الغياب يعني *لا نعرف*.",
            icon="ℹ️",
        )

    with st.expander("أوزان العوامل"):
        st.dataframe(
            pd.DataFrame([
                {"العامل": FACTOR_LABELS[name], "الوزن": f"{weight:.0%}",
                 "محسوب؟": "نعم" if name in risk.known_factors else "لا"}
                for name, weight in FACTOR_WEIGHTS.items()
            ]),
            use_container_width=True, hide_index=True,
        )
        st.caption(
            "معايرة أولية بلا بيانات تحقّق — تُضبط حين يتراكم "
            "`production_plans.actual_quantity` مقابل `planned_quantity`."
        )

    # السجل المحفوظ يخصّ بيانات العرض في القاعدة المحلية. منتج مرفوع لا
    # وجود له فيها، والاستعلام عنه يُرجع فراغاً مضلّلاً ("لا سجل" توحي
    # بأن الحساب لم يُشغَّل، بينما التخزين معطَّل أصلاً).
    _, _, is_user_data = active_dataset()
    if is_user_data or is_hosted():
        st.caption(
            "🔒 سجل النماذج التاريخي متاح في الوضع المحلي فقط — "
            "بياناتك لا تُحفَظ. كل ما فوق محسوب لجلستك الآن."
        )
        return

    st.subheader("سجل النماذج المحفوظ")
    ranking = ForecastRepository(db_path=DATABASE_PATH).model_ranking(product)
    if not ranking:
        st.info(
            "لا سجل محفوظ لهذا المنتج. شغّل الحساب من **النظرة التنفيذية**."
        )
    else:
        st.dataframe(
            pd.DataFrame([
                {
                    "النموذج": row["model_name"],
                    "RMSE": round(row["rmse"], 2) if row["rmse"] is not None else None,
                    "MAE": round(row["mae"], 2) if row["mae"] is not None else None,
                    "الأفضل؟": "★" if row["is_best"] else "",
                    "زمن (ms)": row["training_duration_ms"],
                    "التقييم": row["evaluated_at"],
                }
                for row in ranking
            ]),
            use_container_width=True, hide_index=True,
        )

    stored = RecommendationRepository(db_path=DATABASE_PATH).latest_for_product(product)
    if stored:
        st.subheader("آخر توصية محفوظة")
        st.success(stored.as_message())
        st.caption(stored.reason)
