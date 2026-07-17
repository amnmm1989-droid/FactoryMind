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

# منتج واحد بالنماذج التسعة ~1s — مقبول للحساب الحيّ. الكتالوج كله لا
# (3.3 دقيقة) — تلك مهمة services/batch.py.
CLASS_LABELS = {
    "smooth": "منتظم",
    "erratic": "متذبذب",
    "intermittent": "متقطّع",
    "lumpy": "متكتّل",
    "dead": "بلا مبيعات",
}


def _forecast_chart(months, series, result, forecast_months):
    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=months, y=series, name="فعلي", mode="lines+markers",
        line=dict(color="#1f77b4", width=2),
    ))

    best = result.best
    figure.add_trace(go.Scatter(
        x=forecast_months, y=best.upper_bound, name="حد أعلى 95%",
        mode="lines", line=dict(width=0), showlegend=False,
    ))
    figure.add_trace(go.Scatter(
        x=forecast_months, y=best.lower_bound, name="فترة الثقة 95%",
        mode="lines", line=dict(width=0), fill="tonexty",
        fillcolor="rgba(255,165,0,0.20)",
    ))
    figure.add_trace(go.Scatter(
        x=forecast_months, y=best.forecast_values,
        name=f"تنبؤ {best.model_name}", mode="lines+markers",
        line=dict(color="#ff7f0e", width=2, dash="dash"),
    ))
    figure.update_layout(
        title=f"الطلب الفعلي والمتوقَّع — {best.model_name}",
        xaxis_title="الشهر", yaxis_title="الكمية", height=420,
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
            "النموذج": evaluation.model_name,
            "RMSE" + ("" if by_cumulative else " ★"): round(metrics.rmse, 2),
            "خطأ تراكمي" + (" ★" if by_cumulative else ""): round(metrics.cumulative_error, 1),
            "MAE": round(metrics.mae, 2),
            "MAPE %": round(metrics.mape, 1) if metrics.mape is not None else None,
            "زمن (ms)": evaluation.duration_ms,
        })
    return pd.DataFrame(rows)


def render(months: list[str], products: dict[str, list[float]]) -> None:
    st.title("🔮 التنبؤ")
    st.caption(
        "يُشغّل كل النماذج المنطبقة، يقيّمها على بيانات لم ترَها، ويختار الأفضل بالأدلة."
    )

    with st.sidebar:
        st.header("إعدادات التنبؤ")
        product = st.selectbox("المنتج", sorted(products))
        steps = st.slider("أفق التنبؤ (أشهر)", 1, MAX_FORECAST_STEPS,
                          DEFAULT_FORECAST_STEPS)
        full_family = st.checkbox(
            "كل النماذج التسعة", value=False,
            help="يضيف ETS/SARIMA/Prophet/XGBoost/RandomForest — أبطأ (~1s).",
        )

    series = products[product]
    models = None if full_family else fast_models()

    try:
        with st.spinner("تدريب النماذج وتقييمها..."):
            result = forecast_product(product, series, steps=steps, models=models)
    except AppError as exc:
        st.error(f"تعذّر التنبؤ: {exc.message}")
        st.info(
            "منتج بلا مبيعات كافية لا ينطبق عليه أي نموذج. "
            "هذا رفض صريح لا عطل — راجع صفحة **ذكاء المنتج** لتصنيف الطلب."
        )
        return

    profile = result.profile
    best = result.best

    columns = st.columns(4)
    columns[0].metric("النموذج الفائز", best.model_name)
    columns[1].metric("تنبؤ الشهر القادم", f"{best.next_period_value:,.0f}")
    columns[2].metric("تصنيف الطلب",
                      CLASS_LABELS.get(profile.demand_class.value, profile.demand_class.value))
    columns[3].metric(
        "نماذج قُيِّمت", f"{result.evaluated_count}/{len(result.evaluations)}",
        help="المقيَّم = دُرِّب على جزء من السلسلة واختُبر على الباقي. "
             "صفر يعني أن السلسلة أقصر من أن تُقسَّم — لا أن النماذج فشلت.",
    )

    st.plotly_chart(
        _forecast_chart(months[-len(series):], series, result,
                        [f"+{i+1}" for i in range(steps)]),
        use_container_width=True,
    )

    st.subheader("مقارنة النماذج")
    ranking = result.ranking()

    if not ranking:
        # لا نموذج أمكن تقييمه: السلسلة أقصر من أن تُقسَّم إلى تدريب واختبار
        # بعد اقتطاع النافذة. جدول فارغ هنا يبدو عطلاً؛ وهو ليس كذلك —
        # المحرك اختار بقاعدته المعلنة: بلا أدلة، الأبسط يفوز.
        st.warning(
            f"**لم يُقيَّم أي نموذج.** السلسلة ({profile.non_zero_count} شهراً "
            f"بمبيعات من {len(series)}) أقصر من أن تُقسَّم إلى تدريب واختبار.\n\n"
            f"لذا اختار المحرك **{best.model_name}** بقاعدته المعلنة: بلا دليل "
            "على أن التعقيد يفيد، يفوز الأبسط. الرقم أعلاه تنبؤ حقيقي، لكن "
            "**بلا مقياس دقة يسنده** — تعامل معه بحذر.",
            icon="⚠️",
        )
    else:
        metric_note = (
            "المقياس: **الخطأ التراكمي** — سلسلة متقطّعة، والقرار الإنتاجي "
            "يستهلك إجمالي الأفق لا دقة كل شهر."
            if result.selection_metric == "cumulative_error"
            else "المقياس: **RMSE** — سلسلة منتظمة."
        )
        st.caption(f"{metric_note} العمود المعلَّم ★ هو ما رُتِّب به.")
        st.dataframe(_ranking_table(result), use_container_width=True, hide_index=True)

    failures = [e for e in result.evaluations if not e.succeeded]
    if failures:
        with st.expander(f"نماذج لم تنطبق ({len(failures)})"):
            for evaluation in failures:
                st.write(f"**{evaluation.model_name}** — {evaluation.error}")

    st.subheader("التوصية")
    try:
        recommendation = recommend_production(product, series, best)
        st.success(recommendation.as_message())
        st.caption(recommendation.reason)
    except AppError as exc:
        st.warning(f"تعذّرت التوصية: {exc.message}")
