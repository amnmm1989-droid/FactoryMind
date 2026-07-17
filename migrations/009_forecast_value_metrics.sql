-- 009_forecast_value_metrics.sql
-- ===================================================
-- WAPE و Forecast Value Added — "دقّة عملية" مفهومة، و"هل يستحق النموذج
-- تعقيده؟" كسؤال قابل للقياس عبر الزمن لا تقرير مجمَّد.
--
-- forecasts.wape: WAPE للتنبؤ الفائز على نافذة الاختبار — mae/rmse/mape
-- موجودة هنا لنفس السبب: رقم يُستعلم عنه (ترتيب، تتبّع دقة عبر الزمن).
--
-- forecasts.fva: خطأ Naive ناقص خطأ الفائز، بمقياس الاختيار نفسه (rmse أو
-- cumulative_error). NULL حين لم يُقيَّم Naive أصلاً — لا صفر مصطنع يوهم
-- بمقارنة لم تحدث. راجع services/forecast_engine/engine.py:_forecast_value_added
-- لماذا القياس بمقياس الاختيار لا رقم ثابت.
--
-- model_performance.wape: نفس المبدأ لكل نموذج جُرِّب، لا الفائز وحده —
-- يتّسق مع mae/rmse/mape الموجودين هناك أصلاً لكل تقييم.
--
-- لا عمود fva في model_performance: الـFVA مقارنة (فائز مقابل Naive)، لا
-- خاصية لنموذج منفرد — مكانه forecasts، صفٌّ واحدٌ لكل جولة.
-- ===================================================

ALTER TABLE forecasts ADD COLUMN wape REAL CHECK (wape IS NULL OR wape >= 0);
ALTER TABLE forecasts ADD COLUMN fva REAL;

ALTER TABLE model_performance
    ADD COLUMN wape REAL CHECK (wape IS NULL OR wape >= 0);
