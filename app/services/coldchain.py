"""Cold-chain analysis: outlier flagging, smoothing and a threshold-breach forecast.

Method (deliberately simple and explainable):
  1. filtered = rolling median (window 5) of the raw readings
  2. a reading is an outlier if it is far from the median of its neighbours
     (|residual| > max(4 * 1.4826 * MAD, 1.0 C)); outliers are FLAGGED, never deleted
  3. trend = least-squares line over the last `fit_n` non-outlier filtered points
  4. ETA = (limit - current) / slope   (only if the sample is warming)
"""
from datetime import datetime
from typing import List, Tuple

import numpy as np


def _rolling_median(v: np.ndarray, w: int) -> np.ndarray:
    h = w // 2
    return np.array([np.median(v[max(0, i - h): i + h + 1]) for i in range(len(v))])


def analyze(readings: List[Tuple[datetime, float]], limit_c: float, fit_n: int = 18, horizon_h: int = 10) -> dict:
    if len(readings) < 3:
        return {"status": "nodata", "series": [], "forecast": [], "current": None, "rate_c_per_h": None, "eta_h": None}
    readings = sorted(readings, key=lambda r: r[0])
    t_end = readings[-1][0]
    hrs = np.array([(t - t_end).total_seconds() / 3600 for t, _ in readings])
    raw = np.array([v for _, v in readings], dtype=float)

    med7 = _rolling_median(raw, 7)
    res = raw - med7
    mad = np.median(np.abs(res - np.median(res)))
    thr = max(4 * 1.4826 * mad, 1.0)
    outlier = np.abs(res) > thr
    clean = np.where(outlier, med7, raw)
    filt = _rolling_median(clean, 5)

    idx = np.where(~outlier)[0][-fit_n:]
    slope = float(np.polyfit(hrs[idx], filt[idx], 1)[0]) if len(idx) >= 3 else 0.0
    current = float(filt[idx[-1]]) if len(idx) else float(filt[-1])

    eta = None
    if slope > 0.05 and current < limit_c:
        eta = (limit_c - current) / slope
    if current >= limit_c:
        status = "breached"
    elif eta is not None and eta <= 4:
        status = "critical"
    elif eta is not None and eta <= 12:
        status = "warning"
    else:
        status = "ok"

    series = [{"h": round(float(h), 3), "raw": round(float(r), 2), "filtered": round(float(f), 2), "outlier": bool(o)}
              for h, r, f, o in zip(hrs, raw, filt, outlier)]
    forecast = [{"h": h, "temp": round(current + slope * h, 2)} for h in range(0, horizon_h + 1)]
    return {"status": status, "current": round(current, 2), "rate_c_per_h": round(slope, 3),
            "eta_h": None if eta is None else round(eta, 1), "limit_c": limit_c,
            "outliers": int(outlier.sum()), "series": series, "forecast": forecast}
