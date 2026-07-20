"""
model_tools.py

Layer 2 diagnostic/modeling functions: fit a candidate forecasting model on
a train split, backtest it against a held-out window of real observations,
and return error metrics plus enough detail (AIC, residual diagnostics,
feature importances) for an agent to reason about model fit quality, not
just accuracy.

All functions take a full DataFrame (columns: date, value) and a
holdout_size, and internally split the LAST `holdout_size` rows off as the
test window -- so every model is evaluated against the same held-out period
if called with the same holdout_size.
"""

import numpy as np
import pandas as pd
from scipy.stats import chi2 as _chi2, t as _t_dist
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.stats.diagnostic import acorr_ljungbox
from sklearn.ensemble import GradientBoostingRegressor


def train_test_split(df: pd.DataFrame, holdout_size: int):
    """Split a time-ordered DataFrame into train/test by holding out the
    last `holdout_size` rows. Raises if there isn't enough data.
    """
    if holdout_size >= len(df):
        raise ValueError(
            f"holdout_size ({holdout_size}) must be smaller than the series length ({len(df)})."
        )
    train = df.iloc[:-holdout_size].reset_index(drop=True)
    test = df.iloc[-holdout_size:].reset_index(drop=True)
    return train, test


def compute_metrics(y_true, y_pred) -> dict:
    """MAE, RMSE, and MAPE (%) between actual and predicted values. MAPE
    excludes points where y_true is ~0 to avoid division blow-ups, and
    reports how many points were excluded so that's not silently hidden.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    errors = y_true - y_pred

    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors ** 2)))

    nonzero_mask = np.abs(y_true) > 1e-8
    n_excluded = int((~nonzero_mask).sum())
    if nonzero_mask.any():
        mape = float(np.mean(np.abs(errors[nonzero_mask] / y_true[nonzero_mask])) * 100)
    else:
        mape = None

    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "mape_pct": round(mape, 4) if mape is not None else None,
        "mape_points_excluded_near_zero": n_excluded,
    }


def _bootstrap_metric_ci(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_bootstrap: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> dict:
    """Bootstrap confidence intervals for MAE, RMSE, and MAPE: resample
    PAIRED (actual, predicted) points with replacement n_bootstrap times,
    recompute each metric per resample, and take percentiles. A backtest
    metric computed over a modest holdout_size (often ~30 points) has
    real sampling uncertainty of its own; the point estimate alone
    doesn't show it -- two models scoring MAPE 4.8% and 5.0% might not be
    a meaningfully different result once you see how wide each one's own
    interval is. Deterministic given the same seed.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    n = len(y_true)

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_bootstrap, n))
    resampled_true = y_true[idx]
    resampled_pred = y_pred[idx]
    errors = resampled_true - resampled_pred

    mae_samples = np.mean(np.abs(errors), axis=1)
    rmse_samples = np.sqrt(np.mean(errors**2, axis=1))

    nonzero_mask = np.abs(resampled_true) > 1e-8
    with np.errstate(invalid="ignore", divide="ignore"):
        pct_errors = np.where(nonzero_mask, np.abs(errors / resampled_true), np.nan)
    mape_samples = np.nanmean(pct_errors, axis=1) * 100

    alpha = 1 - confidence_level

    def _percentile_ci(samples):
        samples = samples[~np.isnan(samples)]
        if len(samples) == 0:
            return None, None
        lower = round(float(np.percentile(samples, 100 * alpha / 2)), 4)
        upper = round(float(np.percentile(samples, 100 * (1 - alpha / 2))), 4)
        return lower, upper

    mae_ci = _percentile_ci(mae_samples)
    rmse_ci = _percentile_ci(rmse_samples)
    mape_ci = _percentile_ci(mape_samples)

    return {
        "mae_ci_lower": mae_ci[0],
        "mae_ci_upper": mae_ci[1],
        "rmse_ci_lower": rmse_ci[0],
        "rmse_ci_upper": rmse_ci[1],
        "mape_pct_ci_lower": mape_ci[0],
        "mape_pct_ci_upper": mape_ci[1],
    }


def compute_metrics_with_ci(
    y_true,
    y_pred,
    n_bootstrap: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> dict:
    """compute_metrics's point estimates (MAE, RMSE, MAPE), plus a
    bootstrap confidence interval for each -- see _bootstrap_metric_ci.
    """
    metrics = compute_metrics(y_true, y_pred)
    ci = _bootstrap_metric_ci(y_true, y_pred, n_bootstrap=n_bootstrap, confidence_level=confidence_level, seed=seed)
    return {**metrics, **ci, "ci_confidence_level": confidence_level, "ci_n_bootstrap": n_bootstrap}


def residual_diagnostics(residuals, lags: int = 10, alpha: float = 0.05) -> dict:
    """Ljung-Box test for residual autocorrelation, plus an effect size.
    A high p-value (> alpha) is the reassuring outcome here -- it means we
    fail to reject the null of "residuals are white noise," i.e. the
    model hasn't left obvious structure on the table. A low p-value means
    the model is missing something systematic.

    Also reports the Ljung-Box Q statistic as a multiple of its own
    chi-squared critical value at the given alpha (ljung_box_effect_size)
    -- the same "how far past the boundary" pattern used elsewhere in
    this toolkit (e.g. ts-analyst's KPSS effect size), since a p-value
    alone doesn't distinguish barely-failing from badly-failing this test.
    """
    residuals = np.asarray(residuals, dtype=float)
    residuals = residuals[~np.isnan(residuals)]
    if len(residuals) <= lags:
        return {"error": f"Not enough residuals ({len(residuals)}) for {lags} lags."}

    result = acorr_ljungbox(residuals, lags=[lags], return_df=True)
    q_stat = float(result["lb_stat"].iloc[0])
    p_value = float(result["lb_pvalue"].iloc[0])
    critical_value = float(_chi2.ppf(1 - alpha, df=lags))
    effect_size = round(q_stat / critical_value, 4) if critical_value > 0 else None
    is_white_noise = bool(p_value > alpha)

    return {
        "ljung_box_lags": lags,
        "ljung_box_statistic": round(q_stat, 4),
        "ljung_box_critical_value": round(critical_value, 4),
        "ljung_box_effect_size": effect_size,
        "ljung_box_p_value": round(p_value, 4),
        "residuals_look_like_white_noise": is_white_noise,
        "interpretation": (
            f"Fail to reject null: residuals look like white noise, no obvious structure left "
            f"(Q={round(q_stat, 2)} is {effect_size}x its critical value at alpha={alpha})."
            if is_white_noise
            else f"Reject null: residuals show autocorrelation -- the model is likely missing "
            f"structure (e.g. wrong seasonal period, missing lag, remaining trend). "
            f"Q={round(q_stat, 2)} exceeds its critical value by {effect_size}x."
        ),
    }


def fit_naive_baselines(
    df: pd.DataFrame,
    holdout_size: int = 30,
    seasonal_period: int = 7,
    n_bootstrap: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> dict:
    """Fit two trivial baselines every real candidate should beat:
    - naive: forecast = last observed training value, repeated.
    - seasonal_naive: forecast = value from `seasonal_period` steps back in
      the cycle, repeated/tiled across the holdout window.

    Cheap, fast, and a useful sanity floor -- if a fancier model can't beat
    seasonal_naive, that's an important finding in itself. Each baseline's
    backtest_metrics includes a bootstrap confidence interval (see
    compute_metrics_with_ci); holdout_actuals/holdout_predicted are
    included so a candidate model's forecast can be compared against
    either baseline with diebold_mariano_test.
    """
    train, test = train_test_split(df, holdout_size)
    y_test = test["value"].values

    last_value = train["value"].iloc[-1]
    naive_pred = np.full(shape=holdout_size, fill_value=last_value)

    if len(train) >= seasonal_period:
        seasonal_tail = train["value"].iloc[-seasonal_period:].values
        reps = int(np.ceil(holdout_size / seasonal_period))
        seasonal_naive_pred = np.tile(seasonal_tail, reps)[:holdout_size]
    else:
        seasonal_naive_pred = naive_pred  # not enough history to be seasonal

    ci_kwargs = dict(n_bootstrap=n_bootstrap, confidence_level=confidence_level, seed=seed)
    return {
        "holdout_size": holdout_size,
        "holdout_actuals": [round(float(v), 4) for v in y_test],
        "naive": {
            **compute_metrics_with_ci(y_test, naive_pred, **ci_kwargs),
            "holdout_predicted": [round(float(v), 4) for v in naive_pred],
        },
        "seasonal_naive": {
            "seasonal_period_assumed": seasonal_period,
            **compute_metrics_with_ci(y_test, seasonal_naive_pred, **ci_kwargs),
            "holdout_predicted": [round(float(v), 4) for v in seasonal_naive_pred],
        },
    }


def fit_ets(
    df: pd.DataFrame,
    holdout_size: int = 30,
    seasonal_period: int = 7,
    trend: str = "add",
    seasonal: str = "add",
    damped_trend: bool = False,
    n_bootstrap: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> dict:
    """Fit Holt-Winters exponential smoothing (ETS) on the training split,
    forecast the holdout window, and evaluate against real values.
    backtest_metrics includes a bootstrap confidence interval (see
    compute_metrics_with_ci); holdout_actuals/holdout_predicted let this
    result be compared against another model with diebold_mariano_test.
    """
    train, test = train_test_split(df, holdout_size)
    y_test = test["value"].values

    model = ExponentialSmoothing(
        train["value"],
        trend=trend,
        seasonal=seasonal,
        seasonal_periods=seasonal_period,
        damped_trend=damped_trend,
    )
    fit = model.fit()
    forecast = fit.forecast(holdout_size).values

    return {
        "model": "ETS (Holt-Winters)",
        "params": {"trend": trend, "seasonal": seasonal, "seasonal_period": seasonal_period, "damped_trend": damped_trend},
        "aic": round(float(fit.aic), 2),
        "backtest_metrics": compute_metrics_with_ci(
            y_test, forecast, n_bootstrap=n_bootstrap, confidence_level=confidence_level, seed=seed
        ),
        "residual_diagnostics": residual_diagnostics(fit.resid),
        "holdout_actuals": [round(float(v), 4) for v in y_test],
        "holdout_predicted": [round(float(v), 4) for v in forecast],
    }


def fit_sarima(
    df: pd.DataFrame,
    holdout_size: int = 30,
    order: list = None,
    seasonal_order: list = None,
    n_bootstrap: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> dict:
    """Fit a SARIMA model (via SARIMAX) on the training split, forecast the
    holdout window, and evaluate against real values. backtest_metrics
    includes a bootstrap confidence interval (see compute_metrics_with_ci);
    holdout_actuals/holdout_predicted let this result be compared against
    another model with diebold_mariano_test.

    order: (p, d, q) non-seasonal ARIMA order. Default [1, 1, 1].
    seasonal_order: (P, D, Q, s) seasonal order. Default [1, 1, 1, 7].
    """
    order = tuple(order) if order else (1, 1, 1)
    seasonal_order = tuple(seasonal_order) if seasonal_order else (1, 1, 1, 7)

    train, test = train_test_split(df, holdout_size)
    y_test = test["value"].values

    # Pass a single-column DataFrame, not a Series: statsmodels only hits its
    # deprecated in-place ndarray.shape= reshape (NumPy 2.5+ DeprecationWarning)
    # for 1-D endog. Behavior and results are otherwise identical either way.
    model = SARIMAX(
        train[["value"]],
        order=order,
        seasonal_order=seasonal_order,
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    fit = model.fit(disp=False)
    forecast = fit.get_forecast(steps=holdout_size).predicted_mean.values

    return {
        "model": "SARIMA",
        "params": {"order": list(order), "seasonal_order": list(seasonal_order)},
        "aic": round(float(fit.aic), 2),
        "bic": round(float(fit.bic), 2),
        "backtest_metrics": compute_metrics_with_ci(
            y_test, forecast, n_bootstrap=n_bootstrap, confidence_level=confidence_level, seed=seed
        ),
        "residual_diagnostics": residual_diagnostics(fit.resid),
        "holdout_actuals": [round(float(v), 4) for v in y_test],
        "holdout_predicted": [round(float(v), 4) for v in forecast],
    }


def _build_lag_features(df: pd.DataFrame, lags: list) -> pd.DataFrame:
    """Build lag + calendar features for the gradient-boosted-trees model.
    Drops rows with NaN lags (i.e. the first max(lags) rows)."""
    feat = df.copy()
    for lag in lags:
        feat[f"lag_{lag}"] = feat["value"].shift(lag)
    feat["day_of_week"] = feat["date"].dt.dayofweek
    feat["month"] = feat["date"].dt.month
    feat["time_index"] = np.arange(len(feat))
    feat = feat.dropna().reset_index(drop=True)
    return feat


def fit_gradient_boosted_trees(
    df: pd.DataFrame,
    holdout_size: int = 30,
    lags: list = None,
    n_estimators: int = 200,
    max_depth: int = 3,
    learning_rate: float = 0.05,
    n_bootstrap: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> dict:
    """Fit gradient-boosted trees on lag + calendar features.
    backtest_metrics includes a bootstrap confidence interval (see
    compute_metrics_with_ci); holdout_actuals/holdout_predicted let this
    result be compared against another model with diebold_mariano_test
    (pass n_lags=0 there, since this backtest is one-step-ahead -- see
    below -- and its errors shouldn't be autocorrelated the way a genuine
    multi-step forecast's are).

    IMPORTANT CAVEAT this tool cannot express in its numbers alone: this is
    evaluated ONE-STEP-AHEAD using each holdout point's *true* lagged values
    from the real series -- not a recursive multi-step forecast that feeds
    its own predictions back in as lags (which is what ETS/SARIMA do above).
    This makes its backtest metrics NOT directly apples-to-apples with the
    other models -- it's an easier evaluation setting. Note this explicitly
    when comparing models rather than picking the lowest error number blind.
    """
    lags = lags or [1, 7, 14]
    feat = _build_lag_features(df, lags)

    if holdout_size >= len(feat):
        raise ValueError(
            f"holdout_size ({holdout_size}) must be smaller than the feature-engineered "
            f"series length after dropping {max(lags)} rows for lags ({len(feat)})."
        )

    feature_cols = [f"lag_{lag}" for lag in lags] + ["day_of_week", "month", "time_index"]
    train_feat = feat.iloc[:-holdout_size]
    test_feat = feat.iloc[-holdout_size:]

    X_train, y_train = train_feat[feature_cols], train_feat["value"]
    X_test, y_test = test_feat[feature_cols], test_feat["value"]

    model = GradientBoostingRegressor(
        n_estimators=n_estimators, max_depth=max_depth, learning_rate=learning_rate, random_state=42
    )
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)

    importances = {col: round(float(imp), 4) for col, imp in zip(feature_cols, model.feature_importances_)}

    return {
        "model": "Gradient Boosted Trees (one-step-ahead evaluation)",
        "params": {"lags": lags, "n_estimators": n_estimators, "max_depth": max_depth, "learning_rate": learning_rate},
        "backtest_metrics": compute_metrics_with_ci(
            y_test.values, predictions, n_bootstrap=n_bootstrap, confidence_level=confidence_level, seed=seed
        ),
        "feature_importances": importances,
        "holdout_actuals": [round(float(v), 4) for v in y_test.values],
        "holdout_predicted": [round(float(v), 4) for v in predictions],
        "evaluation_caveat": (
            "This backtest uses true lagged values at each holdout point (one-step-ahead), "
            "not a recursive multi-step forecast. It is an easier evaluation setting than the "
            "multi-step forecasts ETS/SARIMA are scored on above -- do not compare error "
            "numbers directly without accounting for this."
        ),
    }


def diebold_mariano_test(
    actuals: list,
    predicted_a: list,
    predicted_b: list,
    model_a_name: str = "Model A",
    model_b_name: str = "Model B",
    loss: str = "squared",
    n_lags: int = None,
) -> dict:
    """Diebold-Mariano-style test (Diebold & Mariano, 1995) for whether
    two models' forecasts on the SAME holdout have significantly
    different accuracy -- gives this layer's "compare candidates
    honestly" instruction (see ts-forecaster's SKILL.md) actual
    statistical backing instead of eyeballing two error numbers. Without
    this, "SARIMA's MAPE is 4.8% vs seasonal_naive's 5.0%" has no way to
    tell a real difference from noise in a holdout that's often only
    ~30 points.

    Pass `actuals` (the same holdout_actuals from either of the two
    fit_* results being compared -- both should be evaluated against
    the SAME holdout, e.g. same csv_path/holdout_size) and each model's
    `holdout_predicted`. Compares the loss differential
    d_t = g(e_a,t) - g(e_b,t), where g is squared error (loss="squared",
    default) or absolute error (loss="absolute") and e = actual -
    predicted. A negative mean differential favors model A (lower
    average loss); positive favors model B.

    Forecast errors from a single-origin multi-step backtest (like
    fit_ets/fit_sarima's) are typically autocorrelated -- later-horizon
    errors aren't independent of earlier ones. This uses a Newey-West
    (Bartlett-kernel) heteroskedasticity-and-autocorrelation-consistent
    variance estimate of the mean differential, with n_lags defaulting to
    the standard Newey & West (1994) automatic rule
    (floor(4*(n/100)^(2/9))) rather than a value tied to a specific
    forecast horizon. Pass n_lags=0 explicitly to assume independent
    errors instead -- a defensible choice when comparing two ONE-STEP-AHEAD
    backtests specifically (e.g. two fit_gradient_boosted_trees runs).
    Uses a Student's t reference distribution (df = n - 1) for the
    p-value, a standard conservative choice for the small holdout sizes
    typical here, rather than the asymptotic normal approximation.

    IMPORTANT: comparing a genuinely multi-step backtest
    (fit_ets/fit_sarima) against a one-step-ahead backtest
    (fit_gradient_boosted_trees) with this test tells you whether the
    ERROR NUMBERS differ significantly -- it does NOT resolve the
    apples-to-oranges evaluation-setting mismatch documented on
    fit_gradient_boosted_trees itself. Carry that caveat forward
    regardless of what this test says.
    """
    actuals = np.asarray(actuals, dtype=float)
    predicted_a = np.asarray(predicted_a, dtype=float)
    predicted_b = np.asarray(predicted_b, dtype=float)
    n = len(actuals)
    if not (len(predicted_a) == n and len(predicted_b) == n):
        return {
            "error": (
                f"actuals, predicted_a, and predicted_b must all be the same length "
                f"(got {n}, {len(predicted_a)}, {len(predicted_b)})."
            )
        }
    if n < 8:
        return {"error": f"Need at least 8 paired forecast points for a meaningful test, got {n}."}

    errors_a = actuals - predicted_a
    errors_b = actuals - predicted_b

    if loss == "squared":
        loss_a, loss_b = errors_a**2, errors_b**2
    elif loss == "absolute":
        loss_a, loss_b = np.abs(errors_a), np.abs(errors_b)
    else:
        return {"error": f"loss must be 'squared' or 'absolute', got {loss!r}."}

    d = loss_a - loss_b
    d_bar = float(np.mean(d))

    if n_lags is None:
        n_lags = max(1, int(np.floor(4 * (n / 100) ** (2 / 9))))
    n_lags = max(0, min(n_lags, n - 2))

    gamma_0 = float(np.mean((d - d_bar) ** 2))
    long_run_var = gamma_0
    for k in range(1, n_lags + 1):
        weight = 1.0 - k / (n_lags + 1)
        gamma_k = float(np.mean((d[k:] - d_bar) * (d[:-k] - d_bar)))
        long_run_var += 2 * weight * gamma_k

    var_d_bar = long_run_var / n
    if var_d_bar <= 0:
        return {
            "error": (
                "Estimated long-run variance of the loss differential is non-positive -- the two "
                "models' errors may be identical, or the series too short/degenerate for this "
                "test. Try n_lags=0."
            )
        }

    dm_stat = d_bar / np.sqrt(var_d_bar)
    df = n - 1
    p_value = float(2 * (1 - _t_dist.cdf(abs(dm_stat), df=df)))
    is_significant = bool(p_value < 0.05)

    favored = None
    if is_significant:
        favored = model_a_name if d_bar < 0 else model_b_name

    return {
        "n_observations": n,
        "loss": loss,
        "n_lags_used": n_lags,
        "mean_loss_differential": round(d_bar, 6),
        "dm_statistic": round(float(dm_stat), 4),
        "degrees_of_freedom": df,
        "p_value": round(p_value, 4),
        "is_significant_difference": is_significant,
        "favored_model": favored,
        "interpretation": (
            f"Statistically significant difference (p={round(p_value, 4)}): {favored} has "
            f"significantly lower average {loss} loss on this holdout."
            if is_significant
            else (
                f"No statistically significant difference in forecast accuracy (p={round(p_value, 4)}) "
                "on this holdout -- treat the two models as roughly equally accurate here, even if "
                "their point error metrics differ numerically."
            )
        ),
    }
