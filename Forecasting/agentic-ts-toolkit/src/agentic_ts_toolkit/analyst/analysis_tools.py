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
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller, acf, kpss, pacf
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tools.sm_exceptions import InterpolationWarning


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


def _kpss_effect_size(series: pd.Series, regression: str = "c") -> dict:
    """Effect size for the KPSS test: how far the statistic sits from its
    5% critical value, expressed as a ratio.

    KPSS's own p-value is coarse -- statsmodels interpolates it from just
    four lookup-table points (10%, 5%, 2.5%, 1%) and clips it at the
    table's edges. That means a wildly non-stationary series and a barely
    non-stationary one can both report p_value=0.01, with the p-value
    alone giving no way to tell them apart. `effect_size` (kpss_statistic
    / critical_value_5pct) keeps distinguishing magnitude past that
    boundary: comfortably below 1 means well within the stationary
    region; values well above 1 mean the statistic exceeds the 5%
    critical value by that many multiples.

    The InterpolationWarning statsmodels raises when the p-value hits a
    table boundary is suppressed here on purpose: this effect size is
    specifically a more informative answer to the same limitation that
    warning is pointing at, not something being papered over.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=InterpolationWarning)
        kpss_stat, p_value, lags, crit = kpss(series, regression=regression, nlags="auto")

    crit_5pct = float(crit["5%"])
    return {
        "statistic": round(float(kpss_stat), 4),
        "p_value": round(float(p_value), 4),
        "lags": int(lags),
        "critical_value_5pct": crit_5pct,
        "effect_size": round(float(kpss_stat) / crit_5pct, 4),
    }


def _combined_stationarity_interpretation(adf_stationary: bool, kpss_stationary: bool) -> str:
    """Joint ADF/KPSS interpretation. The two tests have opposite null
    hypotheses (ADF: non-stationary; KPSS: stationary), so running both
    and reading them together is standard practice -- each test's blind
    spot is roughly the other's strength.
    """
    if adf_stationary and kpss_stationary:
        return "ADF and KPSS agree: series is likely stationary."
    if not adf_stationary and not kpss_stationary:
        return "ADF and KPSS agree: series is likely non-stationary; differencing may be needed."
    if adf_stationary and not kpss_stationary:
        return (
            "ADF and KPSS disagree: ADF rejects a unit root (stationary) but KPSS "
            "rejects stationarity. This combination commonly indicates the series is "
            "trend-stationary rather than level-stationary -- consider re-running with "
            "kpss_regression='ct', or detrending before further analysis."
        )
    return (
        "ADF and KPSS disagree: ADF fails to reject a unit root (non-stationary) but "
        "KPSS fails to reject stationarity. This combination is often inconclusive -- "
        "both tests can have limited power on short or borderline series; treat "
        "stationarity as genuinely uncertain rather than picking one test's verdict "
        "over the other."
    )


def check_stationarity(df: pd.DataFrame, kpss_regression: str = "c") -> dict:
    """Augmented Dickey-Fuller AND KPSS tests for stationarity, each with
    an effect size, combined into one joint verdict.

    ADF's null hypothesis is that the series has a unit root
    (non-stationary); a small p-value (< 0.05) rejects that, suggesting
    stationarity. KPSS's null hypothesis is the OPPOSITE -- that the
    series IS stationary; a small p-value there rejects stationarity.
    Running both and reading them together is standard practice, because
    each test's blind spot is roughly the other's strength. See
    _combined_stationarity_interpretation for the four-way readout.

    Both tests alone only answer "stationary or not" -- neither says how
    strongly. This also reports:
    - a mean-reversion effect size for ADF (`mean_reversion_lambda`,
      `mean_reversion_half_life_periods` -- see _mean_reversion_effect_size)
    - an effect size for KPSS (`kpss_effect_size` -- see
      _kpss_effect_size), which stays informative even when KPSS's own
      p-value is clipped at a lookup-table boundary.

    Args:
        kpss_regression: "c" (default, stationary around a constant --
            the same implicit null ADF is tested against here) or "ct"
            (stationary around a deterministic trend).
    """
    series = df["value"].dropna()

    adf_result = adfuller(series, autolag="AIC")
    adf_stat, adf_p_value = adf_result[0], adf_result[1]
    adf_stationary = bool(adf_p_value < 0.05)
    reversion = _mean_reversion_effect_size(series.values)

    kpss_result = _kpss_effect_size(series, regression=kpss_regression)
    kpss_stationary = bool(kpss_result["p_value"] >= 0.05)

    reversion_note = (
        f"Mean-reversion half-life is ~{reversion['half_life_periods']} periods "
        "(small = corrects quickly, large = slow even if statistically detectable)."
        if reversion["half_life_periods"] is not None
        else "No finite mean-reversion half-life (lambda >= 0 in the ADF regression)."
    )
    kpss_effect_note = (
        f"KPSS statistic is {kpss_result['effect_size']}x its 5% critical value"
        + (" (comfortably below it)." if kpss_result["effect_size"] < 1 else " (exceeds it).")
    )

    return {
        "adf_statistic": round(float(adf_stat), 4),
        "adf_p_value": round(float(adf_p_value), 4),
        "adf_is_likely_stationary": adf_stationary,
        "mean_reversion_lambda": reversion["lambda"],
        "mean_reversion_half_life_periods": reversion["half_life_periods"],
        "kpss_statistic": kpss_result["statistic"],
        "kpss_p_value": kpss_result["p_value"],
        "kpss_lags": kpss_result["lags"],
        "kpss_critical_value_5pct": kpss_result["critical_value_5pct"],
        "kpss_effect_size": kpss_result["effect_size"],
        "kpss_regression": kpss_regression,
        "kpss_is_likely_stationary": kpss_stationary,
        "interpretation": (
            _combined_stationarity_interpretation(adf_stationary, kpss_stationary)
            + " "
            + reversion_note
            + " "
            + kpss_effect_note
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

    Flags lags whose ACF magnitude exceeds a rough significance threshold
    (1.96/sqrt(n)) and reports an effect size for each -- the ACF value's
    magnitude as a multiple of that threshold. A lag that barely clears the
    threshold and one that clears it by 5x are both just "significant"
    without this; the effect size is what tells them apart.
    """
    series = df["value"].dropna()
    n_lags = min(n_lags, len(series) // 2 - 1)

    acf_vals = acf(series, nlags=n_lags, fft=True)
    pacf_vals = pacf(series, nlags=n_lags)

    # Flag lags with notably high autocorrelation (rough heuristic threshold)
    threshold = 1.96 / np.sqrt(len(series))
    significant_acf_lags = [
        {
            "lag": i,
            "acf": round(float(acf_vals[i]), 4),
            "effect_size": round(abs(float(acf_vals[i])) / threshold, 4),
        }
        for i in range(1, len(acf_vals))
        if abs(acf_vals[i]) > threshold
    ]
    # Strongest first, so capping for brevity below keeps the most
    # significant lags rather than just the earliest ones chronologically.
    significant_acf_lags.sort(key=lambda entry: entry["effect_size"], reverse=True)

    return {
        "n_lags_checked": n_lags,
        "significance_threshold": round(float(threshold), 4),
        "significant_acf_lags": significant_acf_lags[:10],  # cap for brevity, strongest first
        "acf_at_lag_1": round(float(acf_vals[1]), 4) if len(acf_vals) > 1 else None,
        "acf_at_lag_7": round(float(acf_vals[7]), 4) if len(acf_vals) > 7 else None,
        "pacf_at_lag_1": round(float(pacf_vals[1]), 4) if len(pacf_vals) > 1 else None,
    }


def detect_anomalies_zscore(df: pd.DataFrame, z_threshold: float = 3.0) -> dict:
    """Flag points whose value is more than z_threshold standard deviations
    from a rolling mean, i.e. simple anomaly/outlier detection.

    Reports each flagged point's actual z-score as an effect size -- not
    just that it crossed z_threshold, but by how much. A z-score of 3.1 and
    a z-score of 11 both clear a threshold of 3.0, but they're very
    different findings; the threshold alone can't tell them apart.
    """
    series = df["value"]
    rolling_mean = series.rolling(window=14, min_periods=1, center=True).mean()
    rolling_std = series.rolling(window=14, min_periods=1, center=True).std().replace(0, np.nan)

    z_scores = (series - rolling_mean) / rolling_std
    flagged_mask = z_scores.abs() > z_threshold
    flagged = df.loc[flagged_mask, ["date", "value"]].copy()
    flagged["z_score"] = z_scores.loc[flagged_mask]

    # Most extreme first, so capping for brevity below keeps the biggest
    # anomalies rather than just the earliest ones chronologically.
    flagged = flagged.reindex(flagged["z_score"].abs().sort_values(ascending=False).index)

    anomalies = [
        {
            "date": str(row["date"].date()),
            "value": round(float(row["value"]), 3),
            "z_score": round(float(row["z_score"]), 3),
        }
        for _, row in flagged.iterrows()
    ]

    return {
        "z_threshold": z_threshold,
        "n_anomalies_flagged": int(len(flagged)),
        "max_abs_z_score": round(float(flagged["z_score"].abs().max()), 3) if len(flagged) else None,
        "anomalies": anomalies[:15],  # cap for brevity, most extreme first
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
