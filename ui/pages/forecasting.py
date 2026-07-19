# ui/pages/forecasting.py
"""
صفحة التنبؤ — محرك Phase 3 موصولاً بالواجهة أخيراً.

الفرق عن "التحليل المتقدم" (الصفحة القديمة): تلك تُشغّل ETS دائماً وتسمّيه
"نموذج التنبؤ". هذه تُشغّل كل النماذج المنطبقة، تقيّمها على بيانات لم ترَها،
وتعرض الترتيب كاملاً — فيرى المستخدم *لماذا* فاز الفائز، لا الرقم وحده.

الأرقام تستحق التذكير: ETS ترتيبه 8 من 9 على هذا الكتالوج، وProphet لم
يفز ولا مرة من 43. الصفحة القديمة كانت تعرض الأسوأ افتراضياً.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import DEFAULT_FORECAST_STEPS, MAX_FORECAST_STEPS
from core.exceptions import AppError
from services.batch import fast_models
from services.decision_engine import recommend_production
from services.forecast_engine import forecast_product
from ui.data_source import active_granularity
from ui.i18n import error as translate_error
from ui.i18n import format_months, format_reason, format_recommendation, t

# منتج واحد بكل النماذج ~1s — مقبول للحساب الحيّ. الكتالوج كله لا
# (3.3 دقيقة) — تلك مهمة services/batch.py.



def _forecast_chart(months, series, result, forecast_months, granularity):
    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=months, y=series, name=t("fc.actual"), mode="lines+markers",
        line=dict(color="#1f77b4", width=2),
    ))

    best = result.best
    figure.add_trace(go.Scatter(
        x=forecast_months, y=best.upper_bound, name=t("fc.upper"),
        mode="lines", line=dict(width=0), showlegend=False,
    ))
    figure.add_trace(go.Scatter(
        x=forecast_months, y=best.lower_bound, name=t("fc.interval"),
        mode="lines", line=dict(width=0), fill="tonexty",
        fillcolor="rgba(255,165,0,0.20)",
    ))
    figure.add_trace(go.Scatter(
        x=forecast_months, y=best.forecast_values,
        name=t("fc.forecast_of", model=best.model_name), mode="lines+markers",
        line=dict(color="#ff7f0e", width=2, dash="dash"),
    ))
    figure.update_layout(
        title=t("fc.chart_title", model=best.model_name),
        xaxis_title=t(f"granularity.one.{granularity}"),
        yaxis_title=t("common.quantity"), height=420,
        hovermode="x unified", margin=dict(t=50, b=40),
    )
    return figure


def _ranking_table(result) -> pd.DataFrame:
    """ترتيب النماذج بالمقياس الفاعل — والعمود المستخدم مُعلَّم."""
    by_cumulative = result.selection_metric == "cumulative_error"
    rows = []
    for evaluation in result.ranking():
        metrics = evaluation.metrics
        rows.append({
            t("common.model"): evaluation.model_name,
            "RMSE" + ("" if by_cumulative else " ★"): round(metrics.rmse, 2),
            t("fc.cumulative_error") + (" ★" if by_cumulative else ""):
                round(metrics.cumulative_error, 1),
            "MAE": round(metrics.mae, 2),
            "MAPE %": round(metrics.mape, 1) if metrics.mape is not None else None,
            t("common.duration_ms"): evaluation.duration_ms,
        })
    return pd.DataFrame(rows)


def render(months: list[str], products: dict[str, list[float]]) -> None:
    st.title(t("fc.title"))
    st.caption(t("fc.subtitle"))

    granularity = active_granularity()
    unit = t(f"granularity.unit.{granularity}")

    with st.sidebar:
        st.header(t("fc.settings"))
        product = st.selectbox(t("common.product"), sorted(products))
        steps = st.slider(t("fc.horizon", unit=unit), 1, MAX_FORECAST_STEPS,
                          DEFAULT_FORECAST_STEPS)
        full_family = st.checkbox(
            t("common.all_models"), value=False,
            help=t("fc.full_family_help"),
        )

    series = products[product]
    models = None if full_family else fast_models()

    try:
        with st.spinner(t("fc.training")):
            result = forecast_product(product, series, steps=steps, models=models,
                                      granularity=granularity)
    except AppError as exc:
        st.error(t("fc.failed", detail=translate_error(exc)))
        st.info(t("fc.failed_help"))
        return

    profile = result.profile
    best = result.best

    columns = st.columns(4)
    columns[0].metric(t("fc.winner"), best.model_name)
    columns[1].metric(t("fc.next_period"), f"{best.next_period_value:,.0f}")
    columns[2].metric(t("fc.demand_class"), t(f"class.{profile.demand_class.value}"))
    columns[3].metric(
        t("fc.evaluated"), f"{result.evaluated_count}/{len(result.evaluations)}",
        help=t("fc.evaluated_help"),
    )

    st.plotly_chart(
        _forecast_chart(format_months(months[-len(series):]), series, result,
                        [f"+{i+1}" for i in range(steps)], granularity),
        use_container_width=True,
    )

    st.subheader(t("fc.comparison"))
    ranking = result.ranking()

    if not ranking:
        # لا نموذج أمكن تقييمه: السلسلة أقصر من أن تُقسَّم إلى تدريب واختبار
        # بعد اقتطاع النافذة. جدول فارغ هنا يبدو عطلاً؛ وهو ليس كذلك —
        # المحرك اختار بقاعدته المعلنة: بلا أدلة، الأبسط يفوز.
        st.warning(
            t("fc.no_evaluation", nonzero=profile.non_zero_count,
              total=len(series), model=best.model_name, unit=unit),
            icon=":material/warning:",
        )
    else:
        metric_note = t(
            "fc.metric_cumulative" if result.selection_metric == "cumulative_error"
            else "fc.metric_rmse"
        )
        st.caption(t("fc.metric_marked", note=metric_note))
        st.dataframe(_ranking_table(result), use_container_width=True, hide_index=True)

    failures = [e for e in result.evaluations if not e.succeeded]
    if failures:
        with st.expander(t("fc.inapplicable", count=len(failures))):
            for evaluation in failures:
                st.write(f"**{evaluation.model_name}** — {evaluation.error}")

    st.subheader(t("fc.recommendation"))
    try:
        recommendation = recommend_production(product, series, best, granularity=granularity)
        st.success(format_recommendation(recommendation))
        st.caption(format_reason(recommendation))
    except AppError as exc:
        st.warning(t("fc.rec_failed", detail=translate_error(exc)))
