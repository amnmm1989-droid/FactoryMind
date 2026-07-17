# models/statistics.py
import numpy as np
from scipy import stats

def trend_analysis(series):
    x = np.arange(len(series))
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, series)
    # رمز لا نص: هذه طبقة نماذج، والعرض شأن ui/. النص العربي المضمَّن هنا
    # سابقاً كان يظهر حرفياً في واجهة إنجليزية — ولا مكان لترجمته.
    trend_direction = "up" if slope > 0 else "down" if slope < 0 else "flat"
    return {
        'slope': slope,
        'intercept': intercept,
        'r_squared': r_value**2,
        'p_value': p_value,
        'direction': trend_direction
    }

def detect_outliers_iqr(series):
    q1 = np.percentile(series, 25)
    q3 = np.percentile(series, 75)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    outliers = [i for i, val in enumerate(series) if val < lower_bound or val > upper_bound]
    return outliers, lower_bound, upper_bound