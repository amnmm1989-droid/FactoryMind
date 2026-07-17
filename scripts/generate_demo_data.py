#!/usr/bin/env python3
"""
توليد بيانات العرض المرفقة — اصطناعية بالكامل.

    python scripts/generate_demo_data.py

## لماذا اصطناعية

بيانات العرض هي **أول ما يراه كل زائر**، والمستودع عام. أي ملف حقيقي هنا
يعني نشر أرقام مبيعات: الأصناف، والمقاسات، والكميات الشهرية لسنوات. هذا
سرّ تجاري لا عيّنة.

## ولماذا هي *أفضل* للعرض — لا مجرد أأمن

الأداة تقوم على تصنيف الطلب: منتظم يفوز فيه ETS، متقطّع يفوز فيه Croston،
ميت يُرفض. كتالوج حقيقي واحد نادراً ما يُظهر ذلك — بيانات هذا المشروع
الأصلية كانت 84% متقطّعة، فالزائر يرى تصنيفاً واحداً تقريباً ولا يفهم
لماذا بُني كل هذا.

هنا كل صنف مُصمَّم ليُظهر سلوكاً بعينه. الكتالوج **يشرح الأداة**.

## القابلية للتكرار

البذرة ثابتة (SEED)، فالمخرج متطابق في كل تشغيل — والاختبارات تعتمد على
أعداده. تغييرها يعني تحديث الاختبارات التي تؤكّد الأشكال.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

SEED = 20240517
MONTHS = 44          # نفس مدى البيانات السابقة — ثلاث سنوات وثمانية أشهر
START_YEAR, START_MONTH = 2022, 12

ARABIC_MONTHS = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
]

# كتالوج مصنع مكوّنات صناعية — محايد القطاع عمداً: زائر من أي مجال يفهمه،
# ولا يوحي بأن الأداة لصناعة بعينها.
FAMILIES = [
    ("Hydraulic Pump", ["50mm", "75mm", "100mm"]),
    ("Safety Valve", ['1"', '2"', '4"']),
    ("Electric Motor", ["1.5kW", "3kW", "7.5kW"]),
    ("Gearbox", ["Ratio 10:1", "Ratio 25:1", "Ratio 50:1"]),
    ("Bearing Assembly", ["Type A", "Type B", "Type C"]),
    ("Control Panel", ["Basic", "Advanced", "Industrial"]),
    ("Conveyor Belt", ["2m", "5m", "10m"]),
    ("Filter Cartridge", ["Fine", "Coarse", "HEPA"]),
    ("Pressure Sensor", ["0-10 bar", "0-100 bar", "0-250 bar"]),
    ("Coupling", ["Rigid", "Flexible", "Universal"]),
    ("Drive Shaft", ["Short", "Long"]),
    ("Seal Kit", ["Standard", "High-Temp"]),
    ("Cooling Fan", ["200mm", "300mm"]),
]


def month_labels() -> list[str]:
    labels = []
    year, month = START_YEAR, START_MONTH
    for _ in range(MONTHS):
        labels.append(f"{ARABIC_MONTHS[month - 1]} {year}")
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return labels


def smooth(rng: random.Random, base: float, seasonal: float, trend: float) -> list[float]:
    """منتظم: طلب كل شهر + موسمية سنوية + اتجاه. مجال ETS/SARIMA/Prophet."""
    return [
        max(0.0, round(
            base
            + seasonal * math.sin(2 * math.pi * i / 12)
            + trend * i
            + rng.gauss(0, base * 0.08)
        ))
        for i in range(MONTHS)
    ]


def erratic(rng: random.Random, base: float) -> list[float]:
    """متذبذب: يحدث كل شهر تقريباً، لكن بأحجام شديدة التقلب."""
    return [max(0.0, round(rng.lognormvariate(math.log(base), 0.9))) for _ in range(MONTHS)]


def intermittent(rng: random.Random, size: float, every: int) -> list[float]:
    """متقطّع: فجوات منتظمة، أحجام متماسكة. مجال Croston/TSB."""
    series = [0.0] * MONTHS
    for i in range(rng.randint(0, every - 1), MONTHS, every):
        series[i] = max(0.0, round(rng.gauss(size, size * 0.12)))
    return series


def lumpy(rng: random.Random, size: float) -> list[float]:
    """متكتّل: فجوات *و* تقلب — الأصعب على كل النماذج."""
    series = [0.0] * MONTHS
    for i in range(MONTHS):
        if rng.random() < 0.25:
            series[i] = max(0.0, round(rng.lognormvariate(math.log(size), 1.1)))
    return series


def dying(rng: random.Random, base: float) -> list[float]:
    """يموت: نشط ثم يتوقف. يُظهر لماذا يوصي النظام بـ"أنتج 0" بحق."""
    stop = int(MONTHS * 0.6)
    return [
        max(0.0, round(rng.gauss(base, base * 0.15))) if i < stop else 0.0
        for i in range(MONTHS)
    ]


def dead() -> list[float]:
    """بلا مبيعات قط: يُظهر الرفض الصريح — لا نموذج ينطبق."""
    return [0.0] * MONTHS


def new_product(rng: random.Random, base: float) -> list[float]:
    """أُطلق حديثاً: سلسلة قصيرة فعلياً. يُظهر "لم يُقيَّم أي نموذج"."""
    start = MONTHS - 5
    return [
        0.0 if i < start else max(0.0, round(rng.gauss(base, base * 0.2)))
        for i in range(MONTHS)
    ]


def build_catalogue() -> tuple[dict[str, list[float]], dict[str, str]]:
    """كتالوج مُصمَّم ليُظهر كل تصنيف — لا عيّنة عشوائية.

    التوزيع مقصود: منتظم كافٍ ليفوز فيه ETS ويُرى الفرق، ومتقطّع كافٍ
    ليفوز فيه Croston، وحالات حدّية (ميت، جديد) تُظهر الرفض الصريح.

    يُعيد الفئات أيضاً (اسم المنتج -> العائلة/family) — لا تخميناً من اسم
    المنتج لاحقاً، بل نقلاً مباشراً لما تعرفه هذه الدالة فعلاً وقت البناء:
    كل اسم مبنيّ من family أصلاً (f"{family} {variant}")، فتسجيل الفئة هنا
    ليس استنتاجاً، هو نفس الحقيقة التي بُني بها الاسم.
    """
    rng = random.Random(SEED)
    products: dict[str, list[float]] = {}
    category_of: dict[str, str] = {}
    names = [f"{family} {variant}" for family, variants in FAMILIES for variant in variants]
    family_of_name = {
        f"{family} {variant}": family for family, variants in FAMILIES for variant in variants
    }

    generators = [
        # (الدالة، الحصة التقريبية)
        (lambda: smooth(rng, rng.uniform(180, 420), rng.uniform(40, 90), rng.uniform(-2, 4)), 9),
        (lambda: erratic(rng, rng.uniform(60, 140)), 3),
        (lambda: intermittent(rng, rng.uniform(40, 120), rng.randint(2, 4)), 8),
        (lambda: lumpy(rng, rng.uniform(30, 90)), 4),
        (lambda: dying(rng, rng.uniform(80, 200)), 2),
        (lambda: new_product(rng, rng.uniform(50, 150)), 2),
        (lambda: dead(), 1),
    ]

    needed = sum(count for _, count in generators)
    if needed > len(names):
        # القصّ الصامت أسقط أول مرة الحالاتِ الحدّية بالذات (ميت، جديد)
        # لأنها في آخر القائمة — أي أنه حذف بالضبط ما وُجد الكتالوج ليُظهره.
        raise SystemExit(
            f"أسماء غير كافية: {needed} مطلوب، {len(names)} متاح. أضِف إلى FAMILIES."
        )

    index = 0
    for generator, count in generators:
        for _ in range(count):
            name = names[index]
            products[name] = generator()
            category_of[name] = family_of_name[name]
            index += 1
    return products, category_of


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    target = root / "data" / "data.json"

    products, categories = build_catalogue()
    payload = {"months": month_labels(), "products": products, "categories": categories}
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"✓ {len(payload['products'])} منتج × {len(payload['months'])} شهر → {target}")

    # التصنيف الفعلي — يُطبع كي يبقى المولّد صادقاً عن مخرجه
    import sys

    sys.path.insert(0, str(root))
    from services.forecast_engine import classify_demand

    counts: dict[str, int] = {}
    for series in payload["products"].values():
        name = classify_demand(series).demand_class.value
        counts[name] = counts.get(name, 0) + 1
    print("  التصنيف:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
