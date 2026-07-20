"""
analysis_tools.py

The "tools" available to the Layer-1 agent. Each function does one concrete,
well-scoped piece of time series diagnostics and returns a small JSON-safe
dict summary (not raw arrays) so it can cheaply be passed back into an LLM's
context window.

These are plain Python functions today. In agent.py we wrap them with
Claude's tool-use (function calling) so the model decides which to call,
in what order, and how to interpret the results.
"""

import json
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller, acf, pacf
from statsmodels.tsa.seasonal import seasonal_decompose


def basic_stats(df: pd.DataFrame) -> dict:
    """Summary stats: length, date range, missing values, basic distribution."""
    values = df["value"]
    return {
        "n_observations": int(len(df)),
        "start_date": str(df["date"].min().date()),
        "end_date": str(df["date"].max().date()),
        "inferred_frequency": pd.infer_freq(df["date"]) or "irregular",
        "n_missing_values": int(values.isna().sum()),
        "mean": round(float(values.mean()), 3),
        "std": round(float(values.std()), 3),
        "min": round(float(values.min()), 3),
        "max": round(float(values.max()), 3),
    }


def _mean_reversion_effect_size(values: np.ndarray) -> dict:
    """Effect size for the ADF test: how strongly, not just whether, the
    series mean-reverts.

    The ADF test itself only answers "is there a unit root," which says
    nothing about magnitude -- a series can be statistically significantly
    stationary while reverting so slowly it's practically useless for
    short-horizon forecasting, or so quickly the trend/seasonal signal
    barely matters next to it. This fits the classic Ornstein-Uhlenbeck-style
    regression underlying the ADF statistic itself, delta_y_t = lambda *
    y_{t-1} + mu + epsilon_t, via simple OLS (independent of ADF's own
    autolag selection, so it stays interpretable on its own), and reports:

    - lambda: the mean-reversion speed. Negative means reverting (more
      negative = faster); zero or positive means no mean reversion at all.
    - half_life_periods: periods for half of a deviation from the series'
      long-run mean to decay, i.e. -ln(2)/lambda. None when lambda >= 0,
      since there's no finite half-life to report.
    """
    y = np.asarray(values, dtype=float)
    y_lag = y[:-1]
    delta_y = np.diff(y)
    design = np.column_stack([np.ones_like(y_lag), y_lag])
    coeffs, *_ = np.linalg.lstsq(design, delta_y, rcond=None)
    lam = float(coeffs[1])

    half_life = None
    if lam < 0:
        half_life = round(float(-np.log(2) / lam), 2)

    return {
        "lambda": round(lam, 6),
        "half_life_periods": half_life,
    }


def check_stationarity(df: pd.DataFrame) -> dict:
    """Augmented Dickey-Fuller test for stationarity, plus an effect size.

    Null hypothesis: the series has a unit root (i.e. is non-stationary).
    A small p-value (< 0.05) lets us reject that, suggesting stationarity.

    The ADF test alone only answers "is there a unit root" -- it says
    nothing about how strongly the series mean-reverts. This also reports
    a mean-reversion effect size (see _mean_reversion_effect_size): a
    negative `mean_reversion_lambda` with a short
    `mean_reversion_half_life_periods` indicates fast, practically
    meaningful reversion; a lambda near zero (or a very long half-life)
    indicates the series may be statistically stationary but reverts too
    slowly to matter much for short-horizon forecasting.
    """
    series = df["value"].dropna()
    result = adfuller(series, autolag="AIC")
    adf_stat, p_value = result[0], result[1]
    effect_size = _mean_reversion_effect_size(series.values)

    return {
        "adf_statistic": round(float(adf_stat), 4),
        "p_value": round(float(p_value), 4),
        "is_likely_stationary": bool(p_value < 0.05),
        "mean_reversion_lambda": effect_size["lambda"],
        "mean_reversion_half_life_periods": effect_size["half_life_periods"],
        "interpretation": (
            "Reject null hypothesis: series is likely stationary."
            if p_value < 0.05
            else "Fail to reject null hypothesis: series is likely non-stationary "
            "(has trend and/or unit root); differencing may be needed."
        )
        + (
            f" Mean-reversion half-life is ~{effect_size['half_life_periods']} periods"
            " -- a small number here means deviations correct quickly, a large one"
            " means reversion is slow even if statistically detectable."
            if effect_size["half_life_periods"] is not None
            else " No finite mean-reversion half-life (lambda >= 0): the series"
            " isn't mean-reverting by this measure, regardless of the ADF verdict above."
        ),
    }


def seasonal_decomposition_summary(df: pd.DataFrame, period: int = 7) -> dict:
    """Classical seasonal decomposition (additive). Returns the relative
    strength of trend and seasonal components vs. the residual, which is a
    quick proxy for how much seasonality/trend structure exists.

    period=7 assumes daily data with weekly seasonality; pass period=12 for
    monthly data with yearly seasonality, etc.
    """
    series = df.set_index("date")["value"]
    if len(series) < period * 2:
        return {"error": f"Series too short to decompose with period={period}."}

    decomposition = seasonal_decompose(series, model="additive", period=period, extrapolate_trend="freq")

    resid_var = float(np.nanvar(decomposition.resid))
    seasonal_var = float(np.nanvar(decomposition.seasonal))
    trend_var = float(np.nanvar(decomposition.trend))
    total_var = float(np.nanvar(series))

    def strength(component_var):
        # Strength-of-signal heuristic (Hyndman & Athanasopoulos):
        # bounded roughly in [0, 1], higher = stronger component relative to noise.
        denom = component_var + resid_var
        return round(max(0.0, 1 - resid_var / denom), 4) if denom > 0 else 0.0

    return {
        "period_assumed": period,
        "trend_strength": strength(trend_var),
        "seasonal_strength": strength(seasonal_var),
        "residual_variance_share": round(resid_var / total_var, 4) if total_var > 0 else None,
        "interpretation": (
            f"Trend strength {strength(trend_var):.2f} and seasonal strength "
            f"{strength(seasonal_var):.2f} on a 0-1 scale; higher means that "
            "component explains more of the variation relative to noise."
        ),
    }


def acf_pacf_summary(df: pd.DataFrame, n_lags: int = 21) -> dict:
    """Autocorrelation / partial autocorrelation at selected lags. Useful for
    spotting seasonality period and deciding AR/MA order.
    """
    series = df["value"].dropna()
    n_lags = min(n_lags, len(series) // 2 - 1)

    acf_vals = acf(series, nlags=n_lags, fft=True)
    pacf_vals = pacf(series, nlags=n_lags)

    # Flag lags with notably high autocorrelation (rough heuristic threshold)
    threshold = 1.96 / np.sqrt(len(series))
    significant_acf_lags = [i for i in range(1, len(acf_vals)) if abs(acf_vals[i]) > threshold]

    return {
        "n_lags_checked": n_lags,
        "significance_threshold": round(float(threshold), 4),
        "significant_acf_lags": significant_acf_lags[:10],  # cap for brevity
        "acf_at_lag_1": round(float(acf_vals[1]), 4) if len(acf_vals) > 1 else None,
        "acf_at_lag_7": round(float(acf_vals[7]), 4) if len(acf_vals) > 7 else None,
        "pacf_at_lag_1": round(float(pacf_vals[1]), 4) if len(pacf_vals) > 1 else None,
    }


def detect_anomalies_zscore(df: pd.DataFrame, z_threshold: float = 3.0) -> dict:
    """Flag points whose value is more than z_threshold standard deviations
    from a rolling mean, i.e. simple anomaly/outlier detection.
    """
    series = df["value"]
    rolling_mean = series.rolling(window=14, min_periods=1, center=True).mean()
    rolling_std = series.rolling(window=14, min_periods=1, center=True).std().replace(0, np.nan)

    z_scores = (series - rolling_mean) / rolling_std
    flagged = df.loc[z_scores.abs() > z_threshold, ["date", "value"]]

    return {
        "z_threshold": z_threshold,
        "n_anomalies_flagged": int(len(flagged)),
        "anomaly_dates": [str(d.date()) for d in flagged["date"]][:15],  # cap for brevity
    }


# Registry used by agent.py to expose these as callable tools by name.
TOOL_REGISTRY = {
    "basic_stats": basic_stats,
    "check_stationarity": check_stationarity,
    "seasonal_decomposition_summary": seasonal_decomposition_summary,
    "acf_pacf_summary": acf_pacf_summary,
    "detect_anomalies_zscore": detect_anomalies_zscore,
}


if __name__ == "__main__":
    from data_prep import generate_synthetic_series

    df = generate_synthetic_series()
    for name, fn in TOOL_REGISTRY.items():
        print(f"\n--- {name} ---")
        print(json.dumps(fn(df), indent=2))
