#!/usr/bin/env python3
"""
smoke.py — تشغيل خطّ الأنابيب كاملاً بلا واجهة.

المسار الأساسي لهذا المشروع. السبب من التاريخ لا الحدس: `services/`
عُدِّل 22 مرة، بينما `ui/` لم يُلمس منذ Phase 1. المحرّكات (التنبؤ،
الخطورة، القرار) **غير موصولة بالواجهة أصلاً** — فمن يغيّر فيها لن يرى
أثر تغييره في أي لقطة شاشة. هذا السكربت هو المقبض الصحيح.

    python .claude/skills/run-factorymind/smoke.py --fast

يخرج بـ 0 عند النجاح، و1 عند أول فشل حقيقي.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import warnings

# قبل أي استيراد من المشروع: نحن نُشغَّل من داخل .claude/skills/...
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

warnings.filterwarnings("ignore")


def _quiet() -> None:
    """كتم ضجيج cmdstanpy/Prophet — يطبع تقدّم التحسين على stdout."""
    logging.disable(logging.INFO)
    for name in ("cmdstanpy", "prophet", "matplotlib"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def check_schema(db_path: str) -> None:
    """الـ schema مملوكة لـ migrations/ — المستودع يتحقق ولا يُنشئ.

    تخطّي هذا يعطي MigrationError لاحقاً بدل رسالة مفيدة هنا.
    """
    from migrate import missing_tables

    missing = missing_tables(db_path)
    if missing:
        print(f"✗ قاعدة البيانات ناقصة {len(missing)} جدول: {', '.join(missing[:4])}...")
        print("  شغّل: python migrate.py")
        sys.exit(1)
    print(f"✓ الـ schema كاملة ({db_path})")


def load_series(product: str | None) -> tuple[str, list[float]]:
    """قراءة سلسلة من data.json مباشرة — لا حاجة لقاعدة البيانات للتنبؤ."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    with open(os.path.join(root, "data", "data.json"), encoding="utf-8") as handle:
        data = json.load(handle)

    products = data["products"]
    if product:
        matches = [name for name in products if product.lower() in name.lower()]
        if not matches:
            print(f"✗ لا منتج يطابق: {product}")
            sys.exit(1)
        name = matches[0]
    else:
        # الأغنى بياناتً — يُشغّل كل النماذج، فيكشف أعطالها
        name = max(products, key=lambda n: sum(1 for v in products[n] if v > 0))
    return name, products[name]


def run_pipeline(product: str | None, fast: bool, steps: int) -> int:
    from services.decision_engine import recommend_production
    from services.forecast_engine import classify_demand, forecast_product

    name, series = load_series(product)
    non_zero = sum(1 for v in series if v > 0)

    profile = classify_demand(series)
    print(f"\n▸ المنتج: {name[:52]}")
    print(f"  نقاط: {len(series)} | غير صفرية: {non_zero} | "
          f"تصنيف: {profile.demand_class.value} (ADI={profile.adi:.2f})")

    models = None
    if fast:
        # Prophet ~0.5s، XGBoost ~2.2s. استبعادهما يجعل الدورة لحظية.
        from services.forecast_engine.naive import (
            MovingAverageForecaster,
            NaiveForecaster,
        )
        from services.forecast_engine.intermittent import (
            CrostonForecaster,
            TSBForecaster,
        )

        models = [
            NaiveForecaster(),
            MovingAverageForecaster(),
            CrostonForecaster(),
            TSBForecaster(),
        ]
        print("  (--fast: النماذج الخفيفة فقط)")

    started = time.perf_counter()
    result = forecast_product(name, series, steps=steps, models=models, use_cache=False)
    elapsed = time.perf_counter() - started

    # الترتيب بالمقياس الفاعل لا بـ RMSE دائماً — العمود المعلَّم بـ (*) هو
    # ما رُتِّب به. بدون هذا يبدو الجدول غير مرتّب على السلاسل المتقطّعة.
    by_cumulative = result.selection_metric == "cumulative_error"
    rmse_header = "RMSE" if by_cumulative else "RMSE (*)"
    cumulative_header = "تراكمي (*)" if by_cumulative else "تراكمي"

    print(f"\n  محرك التنبؤ — {elapsed:.1f}s")
    print(f"  المقياس: {result.selection_metric} | الفائز: {result.best_model_name}")
    print(f"  {'النموذج':<16}{rmse_header:>10}{cumulative_header:>13}")
    print("  " + "-" * 39)
    for evaluation in result.ranking():
        metrics = evaluation.metrics
        print(f"  {evaluation.model_name:<16}{metrics.rmse:>10.2f}"
              f"{metrics.cumulative_error:>13.1f}")

    failed = [e for e in result.evaluations if not e.succeeded]
    for evaluation in failed:
        print(f"  ⚠ {evaluation.model_name}: {evaluation.error}")

    recommendation = recommend_production(name, series, result.best)
    risk = recommendation.risk
    print(f"\n  محرك القرار")
    print(f"  {recommendation.as_message()}")
    print(f"  خطورة: {risk.score:.0f}/100 ({risk.level.value}) | "
          f"عوامل الخطورة: {len(risk.known_factors)}/5 | مجهول: {len(risk.missing_factors)}")

    # فحوص سلامة — تفشل بصوت مسموع لا بصمت
    assert result.best.forecast_values, "تنبؤ فارغ"
    assert len(result.best.forecast_values) == steps, "طول التنبؤ لا يطابق الأفق"
    assert all(v >= 0 for v in result.best.forecast_values), "تنبؤ بكمية سالبة"
    assert 0 <= risk.score <= 100, "درجة خطورة خارج المجال"
    assert recommendation.recommended_quantity >= 0, "توصية بكمية سالبة"
    print("\n✓ فحوص السلامة نجحت")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="تشغيل محرّكات FactoryMind بلا واجهة"
    )
    parser.add_argument("--product", help="جزء من اسم المنتج (الافتراضي: الأغنى بيانات)")
    parser.add_argument("--fast", action="store_true",
                        help="النماذج الخفيفة فقط — يتخطّى Prophet/XGBoost/RF")
    parser.add_argument("--steps", type=int, default=6, help="أفق التنبؤ (افتراضي 6)")
    parser.add_argument("--db", default=None, help="مسار قاعدة البيانات")
    args = parser.parse_args()

    _quiet()
    from config import DATABASE_PATH

    check_schema(args.db or DATABASE_PATH)
    try:
        return run_pipeline(args.product, args.fast, args.steps)
    except AssertionError as exc:
        print(f"\n✗ فحص سلامة فشل: {exc}")
        return 1
    except Exception as exc:
        print(f"\n✗ {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
