#!/usr/bin/env python3
"""
قياس زمن الدفعة على أحجام كتالوج لم تُختبَر قط — لا تحسين أعمى.

    python scripts/benchmark_catalogue_scale.py [حجم1 حجم2 ...]

## لماذا هذا السكربت موجود

services/batch.py يقيس فعلاً: 29 منتجاً بالنماذج الخفيفة < ثانية. لكن هذا
رقم على 29 فقط. كتالوج M5 المرجعي (مسابقة التنبؤ العالمية) يضمّ 30,490
سلسلة، والحلقة في batch.py:92 تسلسلية بلا توازٍ، وكل حفظ (ForecastRepository،
RecommendationRepository) يفتح اتصال SQLite جديداً بمفرده — فرضيتان عن عنق
الزجاجة المحتمل، لم تُقاسا قط.

القاعدة هنا نفس قاعدة المشروع في كل مكان آخر: **لا تُحسَّن مشكلة لم تُثبَت**.
هذا السكربت يقيس فقط. القرار بعده: إن كان الزمن مقبولاً (ثوانٍ لا دقائق)،
لا تُنفَّذ خطوات التوازي/الاتصال المشترك/DuckDB إطلاقاً — تماماً كما حُذف
core/app_config.py لأنه عالج عيباً لم يُثبَت أنه يستحق العلاج.

## ماذا يُقاس، ولماذا اثنان لا رقم واحد

1. **محرك التنبؤ وحده** (forecast_product لكل منتج، بلا قاعدة بيانات):
   الجزء المرتبط بالمعالجة (CPU) — نماذج خفيفة فقط (Naive/MovingAverage/
   Croston/TSB)، نفس ما يستخدمه "حساب الكتالوج" افتراضياً.
2. **الدفعة الكاملة مع الحفظ** (run_batch، تنبؤ + حفظ في SQLite):
   يضيف عبء الإدخال/الإخراج — وهو مصدر الفرضية الثانية أعلاه.

الفارق بين الاثنين هو عبء قاعدة البيانات وحده — إن كان كبيراً، فالمشكلة
في الاتصال لا في المحرك، وهذا يحدّد أي خطوة لاحقة (إن احتُجنا لها أصلاً)
تستحق الوقت.

## توليد الكتالوج الاصطناعي

بمعزل عمداً عن scripts/generate_demo_data.py: ذاك مولّد مصمَّم ليشرح
الأداة لزائر (كل صنف يُظهر تصنيفاً بعينه، بأسماء واقعية) — غرض عرضي لا
قياسي. هنا الغرض مضاد: كمية لا شرح، فالتوليد أبسط وأسرع عمداً — مزيج
خشن من الأنماط الخمسة يكفي ليكون واقعياً إحصائياً دون حمل غرض المولّد
الآخر. بذرة ثابتة (SEED) لقابلية التكرار، كما في ذاك الملف.
"""
from __future__ import annotations

import math
import random
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.exceptions import AppError  # noqa: E402
from migrate import migrate  # noqa: E402
from services.batch import fast_models, run_batch  # noqa: E402
from services.forecast_engine import forecast_product  # noqa: E402

SEED = 20260717
MONTHS = 44  # نفس مدى بيانات العرض — لا حجماً مختاراً ليناسب القياس


def _series(rng: random.Random) -> list[float]:
    """سلسلة واحدة بنمط عشوائي من خمسة — خشنة عمداً، لا معبِّرة كـFAMILIES."""
    kind = rng.random()
    if kind < 0.15:
        return [0.0] * MONTHS  # ميت — 84% من كتالوج المشروع الحقيقي متقطّع/ميت جزئياً
    if kind < 0.35:
        base = rng.uniform(80, 300)
        return [
            max(0.0, round(base + 40 * math.sin(2 * math.pi * i / 12) + rng.gauss(0, base * 0.1)))
            for i in range(MONTHS)
        ]
    if kind < 0.55:
        return [max(0.0, round(rng.lognormvariate(math.log(rng.uniform(50, 150)), 0.9)))
                for _ in range(MONTHS)]
    if kind < 0.85:
        size = rng.uniform(30, 100)
        every = rng.randint(2, 4)
        series = [0.0] * MONTHS
        for i in range(rng.randint(0, every - 1), MONTHS, every):
            series[i] = max(0.0, round(rng.gauss(size, size * 0.15)))
        return series
    size = rng.uniform(20, 80)
    return [max(0.0, round(rng.lognormvariate(math.log(size), 1.1))) if rng.random() < 0.25
            else 0.0 for _ in range(MONTHS)]


def build_catalogue(size: int) -> dict[str, list[float]]:
    rng = random.Random(SEED)
    return {f"BenchProduct-{i:06d}": _series(rng) for i in range(size)}


def _seed_database(db_path: str, products: dict[str, list[float]]) -> None:
    """يبني الجداول عبر migrate() الحقيقي، ثم يُدخِل الكتالوج مباشرة —
    بلا المرور بـ SQLiteRepository.migrate_from_json (يقرأ data/data.json،
    وهو كتالوج العرض الصغير لا الاصطناعي المطلوب هنا)."""
    migrate(db_path, verbose=False)
    months = [f"2024-{i:02d}" for i in range(1, MONTHS + 1)]

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executemany(
            "INSERT INTO months (name, sort_order) VALUES (?, ?)",
            [(name, i) for i, name in enumerate(months)],
        )
        conn.executemany(
            "INSERT INTO products (name) VALUES (?)",
            [(name,) for name in products],
        )
        product_ids = dict(conn.execute("SELECT name, id FROM products"))
        month_ids = dict(conn.execute("SELECT name, id FROM months"))
        conn.executemany(
            "INSERT INTO sales (product_id, month_id, quantity) VALUES (?, ?, ?)",
            [
                (product_ids[name], month_ids[months[i]], value)
                for name, series in products.items()
                for i, value in enumerate(series)
            ],
        )
        conn.commit()
    finally:
        conn.close()


def measure(size: int) -> None:
    products = build_catalogue(size)
    print(f"\n=== {size:,} منتج × {MONTHS} شهر ===")

    # 1) محرك التنبؤ وحده — بلا قاعدة بيانات
    # منتج ميت (15% من التوليد) يرفع InsufficientDataError — متوقَّع لا
    # عطل، ونفس ما يفعله batch.py: يُتخطّى ولا يُسقط القياس.
    models = fast_models()
    started = time.perf_counter()
    for name, series in products.items():
        try:
            forecast_product(name, series, steps=6, models=models, use_cache=False)
        except AppError:
            pass
    engine_seconds = time.perf_counter() - started
    print(f"المحرك وحده (بلا حفظ):     {engine_seconds:8.2f}s"
          f"  ({engine_seconds / size * 1000:6.2f}ms/منتج)")

    # 2) الدفعة الكاملة — تنبؤ + حفظ SQLite (المسار الحقيقي لزر "حساب الكتالوج")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "bench.db")
        _seed_database(db_path, products)

        started = time.perf_counter()
        report = run_batch(products, use_fast_models=True, db_path=db_path)
        batch_seconds = time.perf_counter() - started

    print(f"الدفعة كاملة (تنبؤ+حفظ):   {batch_seconds:8.2f}s"
          f"  ({batch_seconds / size * 1000:6.2f}ms/منتج)")
    print(f"عبء قاعدة البيانات وحده:  {batch_seconds - engine_seconds:8.2f}s"
          f"  ({(batch_seconds - engine_seconds) / batch_seconds:.0%} من زمن الدفعة)")
    print(f"نجح: {report.succeeded}/{report.total}")


def main() -> None:
    import logging

    # تسجيل سطر لكل منتج (INFO في engine.py/forecast_repository.py) مفيد
    # في الاستخدام العادي، لكنه هنا نفسه عبء I/O يُلوّث القياس المقصود.
    logging.disable(logging.INFO)

    sizes = [int(arg) for arg in sys.argv[1:]] or [1_000, 10_000]
    for size in sizes:
        measure(size)


if __name__ == "__main__":
    main()
