# models/statistics.py
import numpy as np
from scipy import stats

def trend_analysis(series):
    x = np.arange(len(series))
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, series)
    trend_direction = "📈 صاعد" if slope > 0 else "📉 هابط" if slope < 0 else "➡️ مستقر"
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