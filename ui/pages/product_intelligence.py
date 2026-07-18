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


from core.exceptions import AppError
from core.runtime_mode import is_hosted
from domain.entities import RiskLevel
from repositories.forecast_repository import ForecastRepository
from repositories.recommendation_repository import RecommendationRepository
from services.batch import fast_models
from ui.data_source import active_dataset, active_granularity, active_inventory
from ui.i18n import error as translate_error
from ui.i18n import format_months, format_reason, format_recommendation, t
from services.forecast_engine import classify_demand, forecast_product
from services.risk_service import FACTOR_WEIGHTS, compute_risk

def _factor_label(name: str) -> str:
    return t(f"factor.{name}")


def _risk_chart(risk) -> go.Figure:
    """العوامل المعروفة فقط — المجهول لا يُرسم كصفر."""
    known = risk.known_factors
    labels = [_factor_label(name) for name in known]
    values = list(known.values())
    colors = ["#d62728" if v >= 70 else "#ff7f0e" if v >= 30 else "#2ca02c"
              for v in values]

    figure = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=colors, text=[f"{v:.0f}" for v in values],
        textposition="outside",
    ))
    figure.update_layout(
        title=t("pi.factor_chart"), xaxis_range=[0, 110],
        height=280, margin=dict(t=40, b=20, l=10, r=10),
    )
    return figure


def render(months: list[str], products: dict[str, list[float]]) -> None:
    st.title(t("pi.title"))

    with st.sidebar:
        st.header(t("pi.settings"))
        product = st.selectbox(t("common.product"), sorted(products))

    series = products[product]
    profile = classify_demand(series)
    demand_class = profile.demand_class.value

    st.subheader(t("pi.classification"))
    columns = st.columns(4)
    columns[0].metric(t("pi.class"), t(f"class.{demand_class}"))
    columns[1].metric("ADI", f"{profile.adi:.2f}", help=t("pi.adi_help"))
    columns[2].metric("CV²", f"{profile.cv_squared:.2f}", help=t("pi.cv2_help"))
    columns[3].metric(t("pi.selling_months"), f"{profile.non_zero_count}/{len(series)}")
    st.caption(t(f"class.{demand_class}.help"))

    if demand_class == "dead":
        st.warning(t("pi.dead_product"))
        return

    st.plotly_chart(
        go.Figure(go.Scatter(
            x=format_months(months[-len(series):]), y=series, mode="lines+markers",
            line=dict(color="#1f77b4"),
        )).update_layout(
            title=t("pi.history"), height=260, margin=dict(t=40, b=30),
            xaxis_title="", yaxis_title=t("common.quantity"),
        ),
        use_container_width=True,
    )

    inventory = active_inventory()
    granularity = active_granularity()
    try:
        with st.spinner(t("pi.computing_risk")):
            result = forecast_product(product, series, steps=6, models=fast_models(),
                                      granularity=granularity)
            risk = compute_risk(
                product, series, result.best,
                inventory.get(product) if inventory else None,
                granularity=granularity,
            )
    except AppError as exc:
        st.error(t("pi.analysis_failed", detail=translate_error(exc)))
        return

    st.subheader(t("pi.risk_breakdown"))
    columns = st.columns([1, 2])
    with columns[0]:
        badge = {RiskLevel.LOW: "🟢", RiskLevel.MEDIUM: "🟡", RiskLevel.HIGH: "🔴"}
        st.metric(t("pi.score"), f"{risk.score:.0f}/100",
                  delta=f"{badge[risk.level]} {t('risk.' + risk.level.value)}",
                  delta_color="off")
        st.metric(t("common.confidence"), f"{risk.confidence:.0%}",
                  help=t("pi.confidence_help"))
    with columns[1]:
        st.plotly_chart(_risk_chart(risk), use_container_width=True)

    if risk.missing_factors:
        st.info(
            t("pi.missing_factors",
              names="، ".join(_factor_label(n) for n in risk.missing_factors)),
            icon=":material/info:",
        )

    with st.expander(t("pi.weights")):
        st.dataframe(
            pd.DataFrame([
                {t("pi.factor"): _factor_label(name), t("pi.weight"): f"{weight:.0%}",
                 t("pi.computed"): t("common.yes") if name in risk.known_factors
                                   else t("common.no")}
                for name, weight in FACTOR_WEIGHTS.items()
            ]),
            use_container_width=True, hide_index=True,
        )
        st.caption(t("pi.weights_caveat"))

    # السجل المحفوظ يخصّ بيانات العرض في القاعدة المحلية. منتج مرفوع لا
    # وجود له فيها، والاستعلام عنه يُرجع فراغاً مضلّلاً ("لا سجل" توحي
    # بأن الحساب لم يُشغَّل، بينما التخزين معطَّل أصلاً).
    _, _, is_user_data = active_dataset()
    if is_user_data or is_hosted():
        st.caption(t("pi.history_local_only"))
        return

    st.subheader(t("pi.stored_history"))
    ranking = ForecastRepository().model_ranking(product)
    if not ranking:
        st.info(t("pi.no_history"))
    else:
        st.dataframe(
            pd.DataFrame([
                {
                    t("common.model"): row["model_name"],
                    "RMSE": round(row["rmse"], 2) if row["rmse"] is not None else None,
                    "MAE": round(row["mae"], 2) if row["mae"] is not None else None,
                    t("pi.is_best"): "★" if row["is_best"] else "",
                    t("common.duration_ms"): row["training_duration_ms"],
                    t("pi.evaluated_at"): row["evaluated_at"],
                }
                for row in ranking
            ]),
            use_container_width=True, hide_index=True,
        )

    stored = RecommendationRepository().latest_for_product(product)
    if stored:
        st.subheader(t("pi.last_recommendation"))
        st.success(format_recommendation(stored))
        st.caption(format_reason(stored))
