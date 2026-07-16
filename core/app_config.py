# core/app_config.py
"""
طبقة إعدادات جديدة تُكمّل config.py الحالي دون كسره.

المشكلة في config.py الحالي:
  - ينفّذ os.makedirs() عند مجرد الـ import (side effect غير متوقع).
  - لا يدعم متغيرات البيئة (كل شيء hardcoded)، فلا يمكن فصل dev/staging/prod.
  - DATA_SOURCE = 'sqlite' مكتوبة مباشرة في الكود بدل أن تكون قابلة للتهيئة.

الحل هنا: dataclass واحدة `Settings` تُبنى من متغيرات البيئة مع قيم
افتراضية تطابق تماماً القيم الحالية في config.py، بحيث:
  - المشروع الحالي (config.py, app.py, ...) يستمر بالعمل حرفياً كما هو.
  - أي كود جديد (Phase 1+) يستورد من هنا بدلاً من config.py مباشرة.
  - لا شيء يُنفَّذ عند الـ import؛ إنشاء المجلدات يتم صراحة عبر
    settings.ensure_directories() في نقطة إقلاع واحدة (app.py).

خطة الدمج التدريجي المقترحة (لا كسر فوري):
  1. أضف هذا الملف كما هو.
  2. في app.py: استبدل الاستيراد من config بـ:
         from core.app_config import get_settings
         settings = get_settings()
         settings.ensure_directories()
     مع إبقاء config.py كما هو لحين انتقال كل الوحدات تدريجياً.
  3. بعد أن تعتمد كل الوحدات على core.app_config، يمكن حذف
     الدوال المكررة من config.py (أو تحويله لاستيراد من هنا فقط).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # ---- مسارات ----
    base_dir: str = BASE_DIR
    data_file: str = field(default_factory=lambda: os.path.join(BASE_DIR, "data", "data.json"))
    database_path: str = field(default_factory=lambda: os.path.join(BASE_DIR, "data", "app.db"))
    cache_path: str = field(default_factory=lambda: os.path.join(BASE_DIR, "cache"))
    log_path: str = field(default_factory=lambda: os.path.join(BASE_DIR, "logs"))
    export_path: str = field(default_factory=lambda: os.path.join(BASE_DIR, "exports"))
    models_cache_path: str = field(default_factory=lambda: os.path.join(BASE_DIR, "cache", "models"))

    # ---- مصدر البيانات ----
    data_source: str = "sqlite"  # 'sqlite' | 'json'

    # ---- إعدادات واجهة Streamlit ----
    page_title: str = "نظام تحليل وتنبؤ متقدم"
    page_icon: str = "🔮"
    layout: str = "wide"
    initial_sidebar_state: str = "expanded"

    # ---- إعدادات التنبؤ ----
    default_forecast_steps: int = 6
    max_forecast_steps: int = 24
    seasonal_periods: int = 12
    confidence_level: float = 1.96
    min_points_for_ml_models: int = 24  # حد أدنى معقول لـ XGBoost/RF (يُستخدم في المرحلة 3)

    # ---- بيئة التشغيل ----
    environment: str = "development"  # 'development' | 'staging' | 'production'
    log_level: str = "INFO"

    def ensure_directories(self) -> None:
        """ينشئ المجلدات المطلوبة صراحةً. لا يُستدعى تلقائياً عند الـ import."""
        for path in (self.cache_path, self.log_path, self.export_path,
                     self.models_cache_path, os.path.dirname(self.database_path)):
            os.makedirs(path, exist_ok=True)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


def get_settings() -> Settings:
    """يبني Settings من متغيرات البيئة (مع fallback للقيم الحالية في config.py)."""
    return Settings(
        data_source=_env("DATA_SOURCE", "sqlite"),
        environment=_env("APP_ENV", "development"),
        log_level=_env("LOG_LEVEL", "INFO"),
        default_forecast_steps=_env_int("DEFAULT_FORECAST_STEPS", 6),
        max_forecast_steps=_env_int("MAX_FORECAST_STEPS", 24),
        seasonal_periods=_env_int("SEASONAL_PERIODS", 12),
        min_points_for_ml_models=_env_int("MIN_POINTS_ML", 24),
    )
