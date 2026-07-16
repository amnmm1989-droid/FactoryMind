# MIGRATION_GUIDE_PHASE0.md

## كيف تدمج هذه الملفات مع مشروعك الحالي

1. انسخ المجلدات التالية إلى جذر مشروعك (بجانب `app.py`, `config.py`):
   ```
   core/
   domain/
   ```
   وانسخ `tests/test_phase0_foundation.py` إلى مجلد `tests/` الموجود لديك.

2. **لا حاجة لحذف أو تعديل أي ملف حالي.** `config.py` الحالي يستمر
   بالعمل تماماً كما هو؛ `core/app_config.py` طبقة موازية جديدة.

3. للتفعيل الاختياري في `app.py` (تحسين وليس إلزام):
   ```python
   from core.logging_config import setup_logging, get_logger
   from core.app_config import get_settings

   setup_logging()
   logger = get_logger(__name__)
   settings = get_settings()
   settings.ensure_directories()

   logger.info("بدء تشغيل التطبيق | data_source=%s", settings.data_source)
   ```

4. شغّل الاختبارات للتأكد من عدم كسر شيء:
   ```bash
   pytest tests/ -q
   ```
   يجب أن ترى كل الاختبارات القديمة (test_models, test_sqlite_repository)
   + 12 اختبار جديد من Phase 0، كلها خضراء.

5. عند البدء في Phase 1، سنستخدم `domain/entities.py` و
   `core/exceptions.py` داخل `services/` الجديدة — لا تعديل إضافي مطلوب
   الآن.
