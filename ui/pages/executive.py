# ui/pages/executive.py
"""
الصفحة التنفيذية — "ما الذي يحتاج انتباهي؟"

تقرأ من جدولَي recommendations و forecasts، ولا تحسب شيئاً. السبب قياس:
كل النماذج على كتالوج كامل = دقائق. صفحة تحسب عند كل تحميل ميتة.
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


from core.runtime_mode import is_hosted
from domain.entities import InventoryStatus, RiskLevel
from repositories.recommendation_repository import RecommendationRepository
from services.batch import fast_models, run_batch
from services.decision_engine import borrow_recommendation
from services.reconciliation import category_totals
from ui.data_source import active_categories, active_dataset, active_granularity, active_inventory
from ui.i18n import format_reason, t

def _level_badge(level: RiskLevel) -> str:
    return t(f"risk.{level.value}")

# أقل كمية تُعتبر إجراءً. الحدّ ليس تجميلياً:
# Croston/TSB يُنتجان *معدّلاً* (0.4 وحدة/شهر مثلاً)، والتوصية بأفق شهر
# واحد تُرجع الكسر كما هو. قبول أي قيمة > 0 كان يضع "أنتج 0" في جدول
# اسمه "يحتاج قراراً" — تناقض ذاتي رآه أول تشغيل حقيقي.
# 0.5 = ما يُقرَّب إلى وحدة واحدة على الأقل. دون ذلك: لا وحدة كاملة
# متوقَّعة الشهر القادم، فلا قرار إنتاج.
MIN_ACTIONABLE_UNITS = 0.5


def _run_batch_ui(
    products: dict[str, list[float]], full_family: bool,
    inventory: dict[str, InventoryStatus] | None = None,
    granularity: str = "monthly",
) -> None:
    progress = st.progress(0.0, text=t("exec.computing"))

    def on_progress(done: int, total: int, name: str) -> None:
        progress.progress(done / total, text=f"{done}/{total} — {name[:40]}")

    report = run_batch(
        products, use_fast_models=not full_family, inventory=inventory,
        granularity=granularity, on_progress=on_progress,
    )
    progress.empty()

    if report.failure_count:
        st.warning(t("exec.batch_partial", ok=report.succeeded,
                     total=report.total, seconds=report.elapsed_seconds,
                     failed=report.failure_count))
        with st.expander(t("exec.failure_details")):
            for name, reason in report.failed[:20]:
                st.write(f"**{name}** — {reason}")
    else:
        st.success(t("exec.batch_done", count=report.succeeded,
                     seconds=report.elapsed_seconds))


def _format_quantity(value: float) -> str:
    """الكميات الصغيرة بمنزلة عشرية.

    نماذج الطلب المتقطّع تُرجع معدّلات كسرية؛ round() كان يعرض 0.4 كصفر،
    فيقرأ المستخدم "أنتج 0" في جدول "يحتاج قراراً".
    """
    if value < 10:
        return f"{value:.1f}"
    return f"{value:,.0f}"


# فوق هذا الحدّ لم يعد الرقم "دقّة سيئة" بل رقماً بلا معنى: خطأ يفوق
# الطلب نفسه بضعفين. عُرضت قيم 21,149% و76,800% كما هي على الملفين
# الأسبوعي والسنوي — ورقم كهذا في عمود اسمه "الدقّة" يُفقد العمود كلّه
# مصداقيته عند من يقرأه.
WAPE_ABSURD_ABOVE = 200.0


def _format_wape(value: float | None) -> str:
    """WAPE بجانب عوامل الخطورة: تلك تقول "على كم عاملاً بُنيت الدرجة؟"،
    وWAPE يقول "وهل نثق بالرقم نفسه أصلاً؟". em-dash لا صفر حين لم يُحسَب —
    منتج بلا تقييم تاريخي (سلسلة قصيرة عن أن تُقسَّم تدريباً واختباراً)
    ليس دقيقاً 0%، بل غير مقيس.

    فوق WAPE_ABSURD_ABOVE يُعرض الحدّ لا القيمة: الفرق بين 500% و76,800%
    لا يحمل معلومة لمن يقرر — كلاهما "لا تثق بهذا الرقم" — بينما عرض
    الرقم الخام يوحي بدقّة قياس ليست موجودة.
    """
    if value is None:
        return "—"
    if value > WAPE_ABSURD_ABOVE:
        return f">{WAPE_ABSURD_ABOVE:.0f}%"
    return f"{value:.0f}%"


def _format_factors(risk) -> str:
    """«4/5» لا «80%».

    النسبة المئوية بجانب عمود دقّة WAPE تُقرأ حتماً «التنبؤ موثوق 80%»،
    وهي في الحقيقة تعدّ عوامل الخطورة المحسوبة فقط. الكسر يقول ما يعنيه
    ولا يحتمل قراءةً احتمالية.
    """
    known, total = risk.factor_counts
    return f"{known}/{total}"


# عدد صفوف "يحتاج قراراً" المعروضة. ثابت مُسمّى لأن اختبار الأولوية
# يقيس تغطيته للحجم، فلا يجوز أن يفترق الرقمان.
ROWS_SHOWN = 50

SORT_IMPACT = "impact"
SORT_RISK = "risk"
SORT_KEY = "_exec_sort"


def _prioritised(recommendations: list) -> list:
    """ترتيب جدول القرار — بالأثر افتراضاً لا بالخطورة.

    القياس الذي فرض هذا (الملفات الخمسة، 185 منتجاً لكل ملف): بالخطورة
    وحدها كانت الصفوف الخمسون المعروضة تغطّي 20% من الحجم أسبوعياً،
    9% شهرياً، 11% ربعياً، **6% سنوياً** — وأكبر منتج في المصنع خارج
    الشاشة في أربعة ملفات من خمسة. بالأثر تنقلب النسبة، لأن أكبر عشرة
    منتجات تحمل 74-79% من الحجم في الملفات الخمسة جميعاً (باريتو حادّ).

    الترتيب بالخطورة يبقى خياراً صريحاً لا يُحذف: سؤال "ما أكثر ما
    يتذبذب؟" مشروع — لكنه ليس السؤال الذي تُفتَح به شاشةٌ عنوانها
    "يحتاج قراراً".
    """
    if st.session_state.get(SORT_KEY, SORT_IMPACT) == SORT_RISK:
        return sorted(recommendations, key=lambda r: r.risk.score if r.risk else 0,
                      reverse=True)
    return sorted(recommendations, key=lambda r: r.units_at_risk, reverse=True)


def _render_sort_control() -> None:
    # مفاتيح صريحة لا مبنيّة بـ f-string: الترجمة المبنيّة ديناميكياً
    # تفلت من حارس المفاتيح اليتيمة في test_i18n، فيتعفّن نصٌّ حيّ بصمت.
    labels = {SORT_IMPACT: t("exec.sort_impact"), SORT_RISK: t("exec.sort_risk")}
    st.segmented_control(
        t("exec.sort_by"),
        options=[SORT_IMPACT, SORT_RISK],
        format_func=labels.__getitem__,
        default=SORT_IMPACT,
        key=SORT_KEY,
        help=t("exec.sort_help"),
    )


def _to_frame(recommendations) -> pd.DataFrame:
    return pd.DataFrame([
        {
            # 🔗 يبقى ملتصقاً بالاسم أينما ظهر المنتج بعد الاستعارة — لا
            # عمود منفصل قد يُفصَل عن الصف عند الفرز أو التمرير.
            t("common.product"): (
                f"🔗 {r.product_name}" if r.borrowed_from else r.product_name
            ),
            t("common.recommended_qty"): _format_quantity(r.recommended_quantity),
            # مفتاح الترتيب الافتراضي — معروضاً لا مخفياً: ترتيبٌ بعمود
            # غير ظاهر يبدو للقارئ عشوائياً.
            t("common.units_at_risk"): _format_quantity(r.units_at_risk),
            t("common.risk"): round(r.risk.score),
            t("common.level"): _level_badge(r.risk.level),
            t("common.demand_change"): round(r.expected_demand_change_pct, 1),
            t("common.risk_factors"): _format_factors(r.risk),
            t("common.wape"): _format_wape(r.forecast_wape),
            t("common.reason"): format_reason(r),
        }
        for r in recommendations
    ])


def _render_fva_summary(recommendations) -> None:
    """Forecast Value Added — يحوّل ادّعاء الـREADME الثابت ("النماذج
    الساذجة تفوز 60%") إلى مقياس حيّ يتغيّر مع بيانات كل مستخدم.

    fva=None يُستبعد لا يُعامَل صفراً: يعني أن Naive لم يُقيَّم أصلاً في
    هذه الجولة (نماذج مخصَّصة بلا Naive)، لا أن الفائز تعادل معه بالضبط.
    """
    valid = [r for r in recommendations if r.forecast_fva is not None]
    if not valid:
        return
    beat_naive = sum(1 for r in valid if r.forecast_fva > 0)
    st.caption(t(
        "exec.fva_summary",
        total=len(valid), beat=beat_naive,
        pct=(beat_naive / len(valid) * 100) if valid else 0.0,
    ))


def _render_category_totals(categories: dict[str, str], recommendations) -> None:
    """التوفيق الهرمي (Bottom-Up) — إجمالي كل فئة = مجموع توصياتها بالضبط.

    لا يظهر القسم أصلاً حين لا فئات معروفة — لا تُخترَع فئة "أخرى" لتمتلئ
    الشاشة. راجع services/reconciliation.py للسبب: لا تنبؤ مستقل للفئة
    يمكن أن ينحرف عن مجموع منتجاتها، لأنه لا يُحسَب أصلاً.
    """
    if not categories:
        return

    totals = category_totals(categories, recommendations)
    if not totals:
        return

    with st.expander(t("exec.category_totals"), expanded=False):
        st.caption(t("exec.category_totals_help"))
        st.dataframe(
            pd.DataFrame([
                {
                    t("common.category"): row.category,
                    t("common.recommended_qty"): _format_quantity(row.total_quantity),
                    t("common.product_count"): row.product_count,
                }
                for row in totals
            ]),
            use_container_width=True, hide_index=True,
        )


def _render_purchase_plan_status() -> None:
    """إشارة من Purchase Plan — الصفحة الأخرى الوحيدة المتبقية في النطاق —
    حين تكون قد حُسبت فعلاً هذه الجلسة. لا إجبار على زيارتها أولاً؛ إن لم
    تُحسَب بعد، لا يظهر شيء هنا إطلاقاً — لا سطراً فارغاً يملأ الشاشة.
    """
    from ui.pages.purchase_plan import RESULT_KEY as PPLAN_RESULT_KEY

    purchase_plan = st.session_state.get(PPLAN_RESULT_KEY)
    if purchase_plan is None:
        return

    urgent = sum(1 for line in purchase_plan.lines if line.urgency == "urgent")
    st.caption(t(
        "exec.glance_purchase", urgent=urgent, total=len(purchase_plan.lines),
    ))


def _render_no_history_section(
    no_history: list[str], products: dict[str, list[float]], *, ephemeral: bool,
    granularity: str = "monthly",
) -> None:
    """منتج بلا مبيعات إطلاقاً — مرئي هنا، لا غائباً بصمت.

    العطل الذي يسدّه هذا القسم: منتج جديد ومنتج ميت يتطابقان في البيانات
    (أصفار كاملة)، وكان كلاهما يُسقَط بصمت من _compute_in_session
    (`except AppError: pass`) بلا أي ذكر في أي شاشة. لا نميّز الآن بين
    الحالتين من البيانات وحدها — النص يقول ذلك صراحة — لكن المنتج لم يعد
    غائباً، والمستخدم يملك خياراً: استعارة تقدير من منتج مشابه إن كان
    جديداً فعلاً، أو تجاهله إن كان متوقّفاً.
    """
    with st.expander(t("exec.no_history", count=len(no_history))):
        st.caption(t("exec.no_history_help"))
        for name in no_history[:50]:
            st.write(f"- {name}")
        if len(no_history) > 50:
            st.caption(f"… +{len(no_history) - 50}")

        source_options = sorted(name for name in products if name not in no_history)
        if not source_options:
            st.caption(t("exec.borrow_no_source"))
            return

        st.divider()
        st.caption(t("exec.borrow_help"))
        col1, col2 = st.columns(2)
        # لا key ثابت عمداً: no_history يتقلّص بعد كل استعارة ناجحة، وkey
        # ثابت يحمل قيمة سابقة قد تغيب عن options الجديدة فترفع Streamlit
        # استثناءً. بلا key، تُعاد بناء القائمة من options الحالية دائماً.
        target = col1.selectbox(t("exec.borrow_target"), no_history)
        source = col2.selectbox(t("exec.borrow_source"), source_options)

        if st.button(t("exec.borrow_apply"), key="_borrow_apply_btn"):
            borrowed = borrow_recommendation(
                target, source, products[source], granularity=granularity
            )
            if ephemeral:
                current = st.session_state.get("session_recommendations", [])
                current = [r for r in current if r.product_name != target] + [borrowed]
                current.sort(key=lambda r: r.risk.score if r.risk else 0, reverse=True)
                st.session_state["session_recommendations"] = current
            else:
                RecommendationRepository().save(borrowed)
            st.rerun()


def _dataset_signature(
    products: dict[str, list[float]],
    inventory: dict[str, InventoryStatus] | None = None,
) -> str:
    """بصمة تتغيّر بتغيّر البيانات — مفتاح إبطال الـ cache.

    تشمل القيم لا الأسماء فقط: مستخدم يرفع نسخة محدَّثة من ملفه (نفس
    المنتجات، أرقام جديدة) يجب أن يرى إعادة حساب، لا نتائج الأمس. المخزون
    يدخل البصمة لنفس السبب بالضبط: رفع ملف مخزون بعد أن حُسبت التوصيات
    فعلاً يجب أن يُعيد حسابها لتخصم المخزون الجديد، لا أن يبقيها كما كانت
    حتى يُضغَط "إعادة حساب" يدوياً.
    """
    import hashlib

    digest = hashlib.sha256()
    for name in sorted(products):
        digest.update(name.encode("utf-8"))
        digest.update(b"|")
        digest.update(",".join(f"{v:.4f}" for v in products[name]).encode("utf-8"))
        digest.update(b"\n")
    for name in sorted(inventory or {}):
        digest.update(b"inv:")
        digest.update(name.encode("utf-8"))
        digest.update(b"|")
        digest.update(f"{inventory[name].current_stock:.4f}".encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _compute_in_session(
    products: dict[str, list[float]], full_family: bool,
    inventory: dict[str, InventoryStatus] | None = None,
    granularity: str = "monthly",
) -> list:
    """حساب بلا حفظ — لبيانات المستخدم وللوضع المستضاف.

    يُعيد كائنات ProductionRecommendation مباشرةً بدل المرور بقاعدة
    البيانات. ممكن فقط لأن النماذج الخفيفة تُنهي الكتالوج في أقل من ثانية.
    """
    from core.exceptions import AppError
    from services.decision_engine import recommend_production
    from services.forecast_engine import forecast_product

    models = fast_models() if not full_family else None
    progress = st.progress(0.0, text=t("exec.computing"))
    recommendations = []
    total = len(products)

    for index, (name, series) in enumerate(products.items(), start=1):
        try:
            result = forecast_product(name, series, steps=6, models=models,
                                      use_cache=False, granularity=granularity)
            product_inventory = inventory.get(name) if inventory else None
            recommendations.append(
                recommend_production(name, list(series), result.best,
                                      product_inventory, granularity=granularity)
            )
        except AppError:
            pass  # منتج بلا بيانات كافية — متوقَّع، يُتخطّى
        if index % 10 == 0 or index == total:
            progress.progress(index / total, text=f"{index}/{total}")

    progress.empty()
    recommendations.sort(key=lambda r: r.risk.score if r.risk else 0, reverse=True)
    return recommendations


def render(months: list[str], products: dict[str, list[float]]) -> None:
    st.title(t("exec.title"))
    # مستقلة عن وجود توصيات إنتاج كلياً — قسم يسحب من صفحات أخرى، فيجب أن
    # يظهر حتى لو "يحتاج قراراً" أدناه فارغة تماماً (لا توصيات محسوبة بعد).
    _render_purchase_plan_status()

    _, _, is_user_data = active_dataset()
    # بيانات المستخدم لا تُكتب في القرص أبداً، والوضع المستضاف لا يحفظ شيئاً:
    # نسخة واحدة تخدم كل الزوّار وقاعدة البيانات ملف مشترك — الحفظ يعني
    # أن يرى الزائر التالي مبيعات السابق.
    ephemeral = is_user_data or is_hosted()
    inventory = active_inventory()
    granularity = active_granularity()

    with st.sidebar:
        st.header(t("common.compute"))
        full_family = st.checkbox(
            t("common.all_models"), value=False,
            help=t("common.all_models_help"),
        )
        compute = st.button(
            t("exec.recompute"), icon=":material/refresh:", use_container_width=True
        )

    if ephemeral:
        # بصمة البيانات جزء من مفتاح الـ cache — وليست ترفاً.
        # بدونها: تُحسب التوصيات على بيانات العرض، يرفع المستخدم ملفه،
        # فيبقى الشريط الجانبي يقول "ملفك: 3 منتجات" بينما الجدول يعرض
        # كتالوج العرض كاملاً لا يملكه. كشفته لقطة شاشة بعد كل فحص آلي.
        signature = _dataset_signature(products, inventory)
        if compute or st.session_state.get("session_signature") != signature:
            st.session_state["session_recommendations"] = _compute_in_session(
                products, full_family, inventory, granularity
            )
            st.session_state["session_signature"] = signature
        stored = st.session_state["session_recommendations"]
        st.caption(t("exec.ephemeral_user" if is_user_data
                     else "exec.ephemeral_hosted"))
    else:
        if compute:
            _run_batch_ui(products, full_family, inventory, granularity)
            st.rerun()
        # الحدّ يغطّي الكتالوج كاملاً لا 500 ثابتة: التقاطع بين products
        # وأسماء stored أدناه (no_history) يحتاج كل منتج له توصية، لا أعلى
        # 500 خطورة فقط — وإلا ظهر منتج له توصية فعلية كأنه "بلا تاريخ".
        stored = RecommendationRepository().highest_risk(limit=max(500, len(products)))

    # منتج بلا أي توصية — إما بيانات ميتة (44 صفراً) أو منتج جديد لم يُطلَق
    # بعد؛ البيانات لا تميّز بينهما، والقسم أدناه يقول ذلك صراحة بدل إخفاء
    # المنتج تماماً كما كان _compute_in_session يفعل (except AppError: pass).
    no_history = sorted(set(products) - {r.product_name for r in stored})

    if not stored and not no_history:
        st.info(t("exec.empty"))
        return

    if stored:
        actionable = [
            r for r in stored if r.recommended_quantity >= MIN_ACTIONABLE_UNITS
        ]
        idle = [r for r in stored if r.recommended_quantity < MIN_ACTIONABLE_UNITS]
        dormant_risky = [r for r in idle if r.risk.level == RiskLevel.HIGH]
        high_risk_actionable = [r for r in actionable if r.risk.level == RiskLevel.HIGH]

        columns = st.columns(4)
        columns[0].metric(t("exec.kpi_assessed"), len(stored))
        columns[1].metric(t("exec.kpi_actionable"), len(actionable))
        columns[2].metric(t("exec.kpi_high_risk"), len(high_risk_actionable))
        columns[3].metric(
            t("exec.kpi_total_qty"),
            f"{sum(r.recommended_quantity for r in actionable):,.0f}",
        )

        _render_fva_summary(stored)
        _render_category_totals(active_categories(), stored)

        st.subheader(t("exec.needs_decision"))
        st.caption(t("exec.needs_decision_help"))
        _render_sort_control()
        if actionable:
            st.dataframe(
                _to_frame(_prioritised(actionable)[:ROWS_SHOWN]),
                use_container_width=True, hide_index=True,
            )
        else:
            st.info(t("exec.nothing_actionable"))

        if dormant_risky:
            with st.expander(t("exec.dormant_risky", count=len(dormant_risky))):
                st.caption(t("exec.dormant_help", threshold=MIN_ACTIONABLE_UNITS))
                st.dataframe(
                    _to_frame(dormant_risky[:30]), use_container_width=True, hide_index=True
                )
    else:
        st.info(t("exec.empty"))

    if no_history:
        _render_no_history_section(
            no_history, products, ephemeral=ephemeral, granularity=granularity
        )

    st.caption(t("exec.inventory_active") if inventory else t("exec.inventory_caveat"))

    _render_validation_section(products, granularity)


VALIDATION_KEY = "_validation_report"


def _validation_frame(report) -> pd.DataFrame:
    """صفّ لكل منتج قِيست دقّته. غير القابل للقياس لا يُحشر هنا برقم مخترَع."""
    return pd.DataFrame([
        {
            t("common.product"): item.product_name,
            t("pplan.col_class"): t(f"class.{item.demand_class}"),
            t("val.col_origins"): item.origins_tested,
            t("common.wape"): f"{item.wape:.0f}%",
            t("val.col_mase"): f"{item.mase:.2f}" if item.mase is not None else "—",
            t("val.col_vs_naive"): t(
                "val.better" if item.beat_naive else "val.worse"
            ),
            t("common.model"): max(
                item.winning_models, key=item.winning_models.get
            ),
        }
        for item in report.products
        if item.wape is not None
    ])


def _validation_excel(report, provenance=None) -> bytes:
    from io import BytesIO

    from ui.export import write_audit_sheet

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        if provenance is not None:
            write_audit_sheet(writer, provenance)
        _validation_frame(report).to_excel(
            writer, sheet_name=t("val.sheet_measured")[:31], index=False
        )
        unmeasured = [
            (p.product_name, t("val.reason_no_demand")) for p in report.products
            if p.wape is None
        ] + list(report.skipped)
        if unmeasured:
            pd.DataFrame(
                unmeasured,
                columns=[t("common.product"), t("pplan.col_reason")],
            ).to_excel(writer, sheet_name=t("val.sheet_unmeasured")[:31], index=False)
    return buffer.getvalue()



def _validation_provenance(products, granularity, report):
    """سجلّ جولة التحقّق — الدقّة هنا مقيسة دائماً، فتُذكر بلا "—"."""
    from services.batch import fast_models
    from services.provenance import RunProvenance

    dataset = st.session_state.get("uploaded_dataset")
    return RunProvenance(
        products=products,
        granularity=granularity,
        period_count=len(getattr(dataset, "months", []) or []),
        source_name=getattr(dataset, "source_name", None),
        model_scope="fast",
        model_names=[m.name for m in fast_models()],
        warning_codes=[w.code for w in getattr(dataset, "warnings", [])],
        measured_share=(
            report.measured_count / report.total_count if report.total_count else None
        ),
        median_wape=report.median_wape,
        beat_naive_share=report.beat_naive_share,
    )


def _render_validation_section(products: dict[str, list[float]], granularity: str) -> None:
    """«لو استخدمتَ هذه الأداة على تاريخك، ماذا كانت ستقول؟»

    خلف زرّ لا تلقائياً: يُشغّل الأداة عدة مرات على ماضي كل منتج، وهو عمل
    حقيقي لا يجب أن يقع على كل تحميل للصفحة.
    """
    from services.batch import fast_models
    from services.validation import build_validation_report

    with st.expander(t("val.title")):
        st.caption(t("val.explainer"))
        if st.button(t("val.compute"), icon=":material/fact_check:"):
            progress = st.progress(0.0, text=t("exec.computing"))

            def on_progress(done: int, total: int, name: str) -> None:
                progress.progress(done / total, text=f"{done}/{total} — {name[:40]}")

            st.session_state[VALIDATION_KEY] = build_validation_report(
                products, granularity=granularity, models=fast_models(),
                on_progress=on_progress,
            )
            progress.empty()

        report = st.session_state.get(VALIDATION_KEY)
        if report is None:
            st.info(t("val.empty"))
            return

        columns = st.columns(4)
        columns[0].metric(
            t("val.kpi_measured"), f"{report.measured_count}/{report.total_count}",
            help=t("val.kpi_measured_help"),
        )
        columns[1].metric(
            t("val.kpi_wape"),
            f"{report.median_wape:.0f}%" if report.median_wape is not None else "—",
            help=t("val.kpi_wape_help"),
        )
        columns[2].metric(
            t("val.kpi_beat_naive"),
            f"{report.beat_naive_share:.0%}" if report.beat_naive_share is not None else "—",
            help=t("val.kpi_beat_naive_help"),
        )
        columns[3].metric(
            t("val.kpi_mase"),
            f"{report.median_mase:.2f}" if report.median_mase is not None else "—",
            help=t("val.kpi_mase_help"),
        )

        # الصدق أولاً: ما لم يُقَس يُذكَر بحجمه، لا يُطوى
        if report.no_demand_count or report.skipped:
            st.caption(t(
                "val.unmeasured_note",
                no_demand=report.no_demand_count, skipped=len(report.skipped),
            ))

        frame = _validation_frame(report)
        if not frame.empty:
            st.dataframe(frame.head(50), use_container_width=True, hide_index=True)
            st.download_button(
                t("val.download"),
                data=_validation_excel(report, _validation_provenance(
                    products, granularity, report
                )),
                file_name="factorymind-validation.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
