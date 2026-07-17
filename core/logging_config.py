# core/logging_config.py
"""
تهيئة Logging مركزية للنظام بالكامل.

الاستخدام في أي وحدة:
    from core.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("...")

الاستخدام مرة واحدة عند إقلاع التطبيق (app.py):
    from core.logging_config import setup_logging
    setup_logging()

يكتب السجلات إلى:
  - Console (دائماً)
  - logs/app.log (rotating file, حتى لا يكبر بلا حدود)

لا يعتمد على Streamlit حتى يبقى قابلاً لإعادة الاستخدام في سكربتات
مستقلة (مثل scripts/generate_demo_data.py أو migrate.py).
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys

_CONFIGURED = False

DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    log_dir: str = "logs",
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    """يهيّئ الـ root logger مرة واحدة فقط (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    os.makedirs(log_dir, exist_ok=True)
    formatter = logging.Formatter(DEFAULT_FORMAT, datefmt=DEFAULT_DATEFMT)

    root = logging.getLogger()
    root.setLevel(level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # تهدئة اللوغرز الصاخبة من المكتبات الخارجية
    for noisy in ("urllib3", "matplotlib", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """يُرجع logger باسم الوحدة. يستدعي setup_logging تلقائياً إن لم يتم استدعاؤها بعد."""
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name)
