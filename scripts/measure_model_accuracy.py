#!/usr/bin/env python3
"""
قياس دقة النماذج التسعة على الكتالوج التجريبي الفعلي — لا افتراض، تشغيل حقيقي.

    python scripts/measure_model_accuracy.py

## لماذا هذا السكربت موجود

README.md وROADMAP.md يحملان جدول "من يفوز" (Naive 16، Prophet 0، إلخ) على
"43 منتجاً ذا بيانات غنية" — لكن `data/data.json` يحمل **29 منتجاً فقط**
اليوم. 43 > 29: الرقم مستحيل حسابياً على الكتالوج الحالي، ولم يبقَ ملف
أو سكربت في المستودع يُعيد إنتاجه. الرقم كان صحيحاً مرة على كتالوج أكبر
لم يعد موجوداً، وتجمّد في التوثيق بعده — بالضبط ما يحذّر منه هذا المشروع
في مكان آخر: ادّعاء دقة لا يمكن التحقّق منه.

هذا السكربت يجعل الرقم قابلاً لإعادة الإنتاج دائماً: يُشغَّل مرة كلما
تغيّر المحرك أو الكتالوج، والنتيجة تُنسخ حرفياً إلى التوثيق — لا تُكتب
من الذاكرة.
"""
from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.exceptions import AppError  # noqa: E402
from migrate import migrate  # noqa: E402
from repositories.sqlite_repository import SQLiteRepository  # noqa: E402
from services.forecast_engine import forecast_product  # noqa: E402


def main() -> None:
    migrate(verbose=False)
    _, products = SQLiteRepository().load_data()

    wins: dict[str, int] = defaultdict(int)
    rank_sum: dict[str, float] = defaultdict(float)
    rank_count: dict[str, int] = defaultdict(int)
    fva_positive = 0
    fva_measured = 0
    wape_values: list[float] = []
    skipped: list[tuple[str, str]] = []

    for name, series in products.items():
        try:
            result = forecast_product(name, series, steps=6, models=None, use_cache=False)
        except AppError as exc:
            skipped.append((name, exc.message))
            continue

        wins[result.best_model_name] += 1
        for position, evaluation in enumerate(result.ranking(), start=1):
            rank_sum[evaluation.model_name] += position
            rank_count[evaluation.model_name] += 1

        if result.best.fva is not None:
            fva_measured += 1
            if result.best.fva > 0:
                fva_positive += 1
        if result.best.wape is not None:
            wape_values.append(result.best.wape)

    total = sum(wins.values())
    print(f"الكتالوج: {len(products)} منتجاً — {len(skipped)} تعذّر تقييمهم كلياً "
          f"(بيانات ميتة تماماً، لا نموذج ينطبق)")
    for name, msg in skipped:
        print(f"  - {name}: {msg}")

    print(f"\nمن فاز فعلياً (من أصل {total} منتجاً قابلاً للتقييم):")
    for model, count in sorted(wins.items(), key=lambda kv: -kv[1]):
        print(f"  {model:15s} {count:3d}  ({count/total*100:.0f}%)")

    print("\nمتوسط الترتيب (1=الأفضل، بين ما أمكن تقييمه):")
    for model in sorted(rank_count, key=lambda m: rank_sum[m] / rank_count[m]):
        avg_rank = rank_sum[model] / rank_count[model]
        print(f"  {model:15s} {avg_rank:.2f}  (قُيِّم في {rank_count[model]} منتج)")

    if fva_measured:
        print(f"\nFVA: الفائز تفوّق على Naive في {fva_positive}/{fva_measured} "
              f"({fva_positive/fva_measured*100:.0f}%)")
    if wape_values:
        print(f"WAPE للفائز — متوسط {statistics.mean(wape_values):.1f}%، "
              f"وسيط {statistics.median(wape_values):.1f}% (عبر {len(wape_values)} منتج)")


if __name__ == "__main__":
    main()
