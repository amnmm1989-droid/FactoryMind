# services/forecast_engine/cache.py
"""
تخزين مؤقت لنتائج التنبؤ.

⚠️ انحراف مقصود عن خارطة الطريق:
الخارطة تقول "تخزّن *النموذج* في cache/models/ (joblib) مع مفتاح =
hash(product+data)". المخزَّن هنا هو *نتيجة التنبؤ* لا الكائن المُدرَّب.

السبب:
1. الهدف من الـ cache تجنّب إعادة الحساب. تخزين النتيجة يتجنّب التدريب
   *والتنبؤ* معاً؛ تخزين النموذج يتجنّب التدريب وحده.
2. كائنات Prophet/statsmodels المُخلَّلة (pickled) مرتبطة بإصدار المكتبة.
   ترقية statsmodels تجعل كل ملف في الـ cache قنبلة موقوتة: إما يفشل
   التحميل (مزعج لكنه مرئي)، أو — أسوأ — يُحمَّل ويتصرف بشكل مختلف بصمت.
3. نموذج Prophet مُخلَّل يزن ميغابايتات؛ النتيجة كيلوبايتات.

مفتاح الـ hash يشمل السلسلة نفسها، فتغيّر البيانات = مفتاح جديد = لا
نتيجة قديمة. عمود data_hash في جدول forecasts يستخدم نفس الدالة.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Sequence

import joblib

from config import CACHE_PATH
from core.logging_config import get_logger

from .base import ForecastOutput
from .evaluation import ModelMetrics

logger = get_logger(__name__)

MODELS_CACHE_DIR = os.path.join(CACHE_PATH, "models")

# صيغة المحتوى المخزَّن. زِدها عند تغيير بنية CachedForecast — الملفات
# القديمة تُتجاهَل تلقائياً بدل أن تُحمَّل بشكل خاطئ.
CACHE_VERSION = 1


@dataclass(frozen=True)
class CachedForecast:
    output: ForecastOutput
    metrics: ModelMetrics | None
    version: int = CACHE_VERSION


def data_hash(product_name: str, series: Sequence[float]) -> str:
    """بصمة (المنتج + بياناته). نفس الدالة تملأ forecasts.data_hash.

    تُقرَّب القيم إلى 6 منازل قبل التجزئة: فروق الفاصلة العائمة تحت هذا
    الحد لا تغيّر تنبؤاً بأي معنى عملي، ولا يجب أن تُبطل الـ cache.
    """
    digest = hashlib.sha256()
    digest.update(product_name.encode("utf-8"))
    digest.update(b"|")
    digest.update(",".join(f"{float(v):.6f}" for v in series).encode("utf-8"))
    return digest.hexdigest()


def cache_key(product_name: str, series: Sequence[float], model_name: str, steps: int) -> str:
    """مفتاح الـ cache = بصمة البيانات + النموذج + الأفق.

    الأفق جزء من المفتاح: تنبؤ بـ 6 أشهر ليس بادئة تنبؤ بـ 12 — النماذج
    التكرارية (الأشجار) تُنتج مساراً مختلفاً لكل أفق.
    """
    digest = hashlib.sha256()
    digest.update(data_hash(product_name, series).encode("utf-8"))
    digest.update(f"|{model_name}|{steps}|v{CACHE_VERSION}".encode("utf-8"))
    return digest.hexdigest()[:32]


def _cache_path(key: str) -> str:
    return os.path.join(MODELS_CACHE_DIR, f"{key}.joblib")


def load(key: str) -> CachedForecast | None:
    """قراءة من الـ cache. أي فشل = تجاهل صامت وإعادة حساب.

    الـ cache تحسين لا مصدر حقيقة: ملف تالف أو من إصدار قديم يجب أن
    يُبطئ التطبيق، لا أن يُسقطه.
    """
    path = _cache_path(key)
    if not os.path.exists(path):
        return None

    try:
        cached = joblib.load(path)
    except Exception as exc:
        logger.warning("Cache read failed | key=%s | %s", key[:8], exc)
        return None

    if not isinstance(cached, CachedForecast) or cached.version != CACHE_VERSION:
        logger.debug("Cache version mismatch | key=%s", key[:8])
        return None

    return cached


def save(key: str, output: ForecastOutput, metrics: ModelMetrics | None) -> None:
    """كتابة في الـ cache. الفشل لا يُوقف شيئاً — النتيجة محسوبة أصلاً."""
    os.makedirs(MODELS_CACHE_DIR, exist_ok=True)
    try:
        joblib.dump(CachedForecast(output=output, metrics=metrics), _cache_path(key))
    except Exception as exc:
        logger.warning("Cache write failed | key=%s | %s", key[:8], exc)


def clear() -> int:
    """تفريغ الـ cache. يُرجع عدد الملفات المحذوفة."""
    if not os.path.isdir(MODELS_CACHE_DIR):
        return 0

    removed = 0
    for filename in os.listdir(MODELS_CACHE_DIR):
        if filename.endswith(".joblib"):
            os.remove(os.path.join(MODELS_CACHE_DIR, filename))
            removed += 1
    return removed
