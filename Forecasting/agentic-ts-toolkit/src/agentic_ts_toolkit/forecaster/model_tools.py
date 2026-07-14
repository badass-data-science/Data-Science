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


def residual_diagnostics(residuals, lags: int = 10) -> dict:
    """Ljung-Box test for residual autocorrelation. A high p-value (> 0.05)
    is the reassuring outcome here -- it means we fail to reject the null
    of "residuals are white noise," i.e. the model hasn't left obvious
    structure on the table. A low p-value means the model is missing
    something systematic.
    """
    residuals = np.asarray(residuals, dtype=float)
    residuals = residuals[~np.isnan(residuals)]
    if len(residuals) <= lags:
        return {"error": f"Not enough residuals ({len(residuals)}) for {lags} lags."}

    result = acorr_ljungbox(residuals, lags=[lags], return_df=True)
    p_value = float(result["lb_pvalue"].iloc[0])
    return {
        "ljung_box_lags": lags,
        "ljung_box_p_value": round(p_value, 4),
        "residuals_look_like_white_noise": bool(p_value > 0.05),
        "interpretation": (
            "Fail to reject null: residuals look like white noise, no obvious structure left."
            if p_value > 0.05
            else "Reject null: residuals show autocorrelation -- the model is likely missing "
            "structure (e.g. wrong seasonal period, missing lag, remaining trend)."
        ),
    }


def fit_naive_baselines(df: pd.DataFrame, holdout_size: int = 30, seasonal_period: int = 7) -> dict:
    """Fit two trivial baselines every real candidate should beat:
    - naive: forecast = last observed training value, repeated.
    - seasonal_naive: forecast = value from `seasonal_period` steps back in
      the cycle, repeated/tiled across the holdout window.

    Cheap, fast, and a useful sanity floor -- if a fancier model can't beat
    seasonal_naive, that's an important finding in itself.
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

    return {
        "holdout_size": holdout_size,
        "naive": compute_metrics(y_test, naive_pred),
        "seasonal_naive": {
            "seasonal_period_assumed": seasonal_period,
            **compute_metrics(y_test, seasonal_naive_pred),
        },
    }


def fit_ets(
    df: pd.DataFrame,
    holdout_size: int = 30,
    seasonal_period: int = 7,
    trend: str = "add",
    seasonal: str = "add",
    damped_trend: bool = False,
) -> dict:
    """Fit Holt-Winters exponential smoothing (ETS) on the training split,
    forecast the holdout window, and evaluate against real values.
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
        "backtest_metrics": compute_metrics(y_test, forecast),
        "residual_diagnostics": residual_diagnostics(fit.resid),
    }


def fit_sarima(
    df: pd.DataFrame,
    holdout_size: int = 30,
    order: list = None,
    seasonal_order: list = None,
) -> dict:
    """Fit a SARIMA model (via SARIMAX) on the training split, forecast the
    holdout window, and evaluate against real values.

    order: (p, d, q) non-seasonal ARIMA order. Default [1, 1, 1].
    seasonal_order: (P, D, Q, s) seasonal order. Default [1, 1, 1, 7].
    """
    order = tuple(order) if order else (1, 1, 1)
    seasonal_order = tuple(seasonal_order) if seasonal_order else (1, 1, 1, 7)

    train, test = train_test_split(df, holdout_size)
    y_test = test["value"].values

    model = SARIMAX(
        train["value"],
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
        "backtest_metrics": compute_metrics(y_test, forecast),
        "residual_diagnostics": residual_diagnostics(fit.resid),
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
) -> dict:
    """Fit gradient-boosted trees on lag + calendar features.

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
        "backtest_metrics": compute_metrics(y_test.values, predictions),
        "feature_importances": importances,
        "evaluation_caveat": (
            "This backtest uses true lagged values at each holdout point (one-step-ahead), "
            "not a recursive multi-step forecast. It is an easier evaluation setting than the "
            "multi-step forecasts ETS/SARIMA are scored on above -- do not compare error "
            "numbers directly without accounting for this."
        ),
    }
