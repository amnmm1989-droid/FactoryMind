# services/analytics.py
import numpy as np
import pandas as pd
from config import SEASONAL_PERIODS

def compute_basic_stats(series):
    """حساب الإحصائيات الأساسية"""
    total = np.sum(series)
    avg = np.mean(series)
    max_val = np.max(series)
    min_val = min([v for v in series if v > 0], default=0)
    std_val = np.std(series)
    median_val = np.median(series)
    cv = std_val / avg if avg != 0 else 0
    non_zero_count = np.sum(np.array(series) > 0)
    last_val = series[-1] if len(series) > 0 else 0
    return {
        'total': total,
        'avg': avg,
        'max': max_val,
        'min': min_val,
        'std': std_val,
        'median': median_val,
        'cv': cv,
        'non_zero_count': non_zero_count,
        'last_val': last_val
    }

def prepare_forecast_months(last_month_idx, months, steps):
    """توليد أسماء الأشهر المتوقعة"""
    forecast_months = []
    for i in range(1, steps + 1):
        next_idx = (last_month_idx + i) % len(months)
        forecast_months.append(months[next_idx])
    return forecast_months

def prepare_seasonal_data(selected_months, series):
    """تحضير البيانات للتحليل الموسمي (أرباع السنة)"""
    df = pd.DataFrame({'الشهر': selected_months, 'الكمية': series})
    n = len(df)
    quarter_size = n // 4
    remainder = n % 4
    quarters = []
    for i in range(4):
        size = quarter_size + (1 if i < remainder else 0)
        quarters.extend([f'الربع {i+1}'] * size)
    if len(quarters) < n:
        quarters.extend(['الربع 4'] * (n - len(quarters)))
    df['الربع'] = quarters[:n]
    seasonal_avg = df.groupby('الربع')['الكمية'].mean().reset_index()
    seasonal_avg['الربع'] = pd.Categorical(seasonal_avg['الربع'],
                                           categories=['الربع 1', 'الربع 2', 'الربع 3', 'الربع 4'],
                                           ordered=True)
    seasonal_avg = seasonal_avg.sort_values('الربع')
    return seasonal_avg