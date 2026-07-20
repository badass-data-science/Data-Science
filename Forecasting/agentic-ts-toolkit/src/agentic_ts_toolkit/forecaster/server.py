"""
server.py — FastMCP server for the Layer 2 forecaster tools.

Wraps model_tools.py as typed MCP tools: fit a candidate model, backtest it
on a held-out window, and return error metrics plus diagnostics (AIC,
residual autocorrelation, feature importances) so the agent can reason
about model quality, not just chase the lowest error number.

Run over stdio (how OpenClaw will launch it), after `pip install -e .`:
    ts-forecaster-server
    # or: python -m agentic_ts_toolkit.forecaster.server
"""

from typing import Optional

from fastmcp import FastMCP

from agentic_ts_toolkit.data_prep import load_series
from .model_tools import (
    fit_naive_baselines as _fit_naive_baselines,
    fit_ets as _fit_ets,
    fit_sarima as _fit_sarima,
    fit_gradient_boosted_trees as _fit_gradient_boosted_trees,
    train_test_split as _train_test_split,
    diebold_mariano_test as _diebold_mariano_test,
)

mcp = FastMCP("ts-forecaster")


@mcp.tool()
def holdout_split_summary(
    csv_path: str,
    holdout_size: int = 30,
    date_col: str = "date",
    value_col: str = "value",
) -> dict:
    """Report the train/test date ranges for a given holdout size, without
    fitting anything. Call this first to sanity-check the split before
    fitting candidate models against it.

    Args:
        csv_path: Path to a CSV with a date column and a value column.
        holdout_size: Number of most-recent observations to hold out as the
            backtest window.
        date_col: Name of the date column in the CSV.
        value_col: Name of the value column in the CSV.
    """
    df = load_series(csv_path, date_col, value_col)
    train, test = _train_test_split(df, holdout_size)
    return {
        "n_total": len(df),
        "n_train": len(train),
        "n_test": len(test),
        "train_range": [str(train["date"].min().date()), str(train["date"].max().date())],
        "test_range": [str(test["date"].min().date()), str(test["date"].max().date())],
    }


@mcp.tool()
def fit_naive_baselines(
    csv_path: str,
    holdout_size: int = 30,
    seasonal_period: int = 7,
    n_bootstrap: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
    date_col: str = "date",
    value_col: str = "value",
) -> dict:
    """Fit two trivial baselines every real candidate model should beat:
    a flat naive forecast (repeat the last training value) and a seasonal
    naive forecast (repeat the value from `seasonal_period` steps back).
    Always run this first -- it's the floor any fancier model must clear.
    Each baseline's backtest metrics include a bootstrap confidence
    interval, and both include holdout_actuals/holdout_predicted so a
    later candidate can be compared against either baseline with
    diebold_mariano_test.

    Args:
        csv_path: Path to a CSV with a date column and a value column.
        holdout_size: Number of most-recent observations to backtest against.
        seasonal_period: Assumed seasonal cycle length for seasonal_naive.
        n_bootstrap: Bootstrap resamples for the backtest metrics' CIs.
        confidence_level: Confidence level for those CIs, e.g. 0.95 for 95%.
        seed: Random seed for the bootstrap, for reproducibility.
        date_col: Name of the date column in the CSV.
        value_col: Name of the value column in the CSV.
    """
    df = load_series(csv_path, date_col, value_col)
    return _fit_naive_baselines(
        df,
        holdout_size=holdout_size,
        seasonal_period=seasonal_period,
        n_bootstrap=n_bootstrap,
        confidence_level=confidence_level,
        seed=seed,
    )


@mcp.tool()
def fit_ets(
    csv_path: str,
    holdout_size: int = 30,
    seasonal_period: int = 7,
    trend: str = "add",
    seasonal: str = "add",
    damped_trend: bool = False,
    n_bootstrap: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
    date_col: str = "date",
    value_col: str = "value",
) -> dict:
    """Fit Holt-Winters exponential smoothing (ETS) on the training split,
    forecast the holdout window, and return backtest error metrics
    (including a bootstrap confidence interval) plus AIC and a residual
    autocorrelation diagnostic (Ljung-Box, with its own effect size).
    Also returns holdout_actuals/holdout_predicted so this result can be
    compared against another model with diebold_mariano_test.

    Args:
        csv_path: Path to a CSV with a date column and a value column.
        holdout_size: Number of most-recent observations to backtest against.
        seasonal_period: Seasonal cycle length (e.g. 7 for weekly in daily data).
        trend: "add", "mul", or None.
        seasonal: "add", "mul", or None.
        damped_trend: Whether to damp the trend component.
        n_bootstrap: Bootstrap resamples for the backtest metrics' CI.
        confidence_level: Confidence level for that CI, e.g. 0.95 for 95%.
        seed: Random seed for the bootstrap, for reproducibility.
        date_col: Name of the date column in the CSV.
        value_col: Name of the value column in the CSV.
    """
    df = load_series(csv_path, date_col, value_col)
    return _fit_ets(
        df,
        holdout_size=holdout_size,
        seasonal_period=seasonal_period,
        trend=trend,
        seasonal=seasonal,
        damped_trend=damped_trend,
        n_bootstrap=n_bootstrap,
        confidence_level=confidence_level,
        seed=seed,
    )


@mcp.tool()
def fit_sarima(
    csv_path: str,
    holdout_size: int = 30,
    order: Optional[list] = None,
    seasonal_order: Optional[list] = None,
    n_bootstrap: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
    date_col: str = "date",
    value_col: str = "value",
) -> dict:
    """Fit a SARIMA model on the training split, forecast the holdout
    window, and return backtest error metrics (including a bootstrap
    confidence interval) plus AIC/BIC and a residual autocorrelation
    diagnostic (Ljung-Box, with its own effect size). Also returns
    holdout_actuals/holdout_predicted so this result can be compared
    against another model with diebold_mariano_test.

    Args:
        csv_path: Path to a CSV with a date column and a value column.
        holdout_size: Number of most-recent observations to backtest against.
        order: [p, d, q] non-seasonal ARIMA order. Defaults to [1, 1, 1].
        seasonal_order: [P, D, Q, s] seasonal order. Defaults to [1, 1, 1, 7].
        n_bootstrap: Bootstrap resamples for the backtest metrics' CI.
        confidence_level: Confidence level for that CI, e.g. 0.95 for 95%.
        seed: Random seed for the bootstrap, for reproducibility.
        date_col: Name of the date column in the CSV.
        value_col: Name of the value column in the CSV.
    """
    df = load_series(csv_path, date_col, value_col)
    return _fit_sarima(
        df,
        holdout_size=holdout_size,
        order=order,
        seasonal_order=seasonal_order,
        n_bootstrap=n_bootstrap,
        confidence_level=confidence_level,
        seed=seed,
    )


@mcp.tool()
def fit_gradient_boosted_trees(
    csv_path: str,
    holdout_size: int = 30,
    lags: Optional[list] = None,
    n_estimators: int = 200,
    max_depth: int = 3,
    learning_rate: float = 0.05,
    n_bootstrap: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
    date_col: str = "date",
    value_col: str = "value",
) -> dict:
    """Fit gradient-boosted trees on lag + calendar features and backtest
    on the holdout window. NOTE: this is evaluated one-step-ahead using
    true lagged values, not a recursive multi-step forecast -- it is an
    easier evaluation setting than fit_ets/fit_sarima above, and the tool
    result flags this explicitly. Don't compare its error numbers directly
    against ETS/SARIMA without accounting for that. Backtest metrics
    include a bootstrap confidence interval; holdout_actuals/
    holdout_predicted let this result be compared against another model
    with diebold_mariano_test (pass n_lags=0 there, since this backtest's
    errors are one-step-ahead, not genuinely autocorrelated the way a
    multi-step forecast's are).

    Args:
        csv_path: Path to a CSV with a date column and a value column.
        holdout_size: Number of most-recent observations to backtest against.
        lags: List of lag steps to use as features. Defaults to [1, 7, 14].
        n_estimators: Number of boosting stages.
        max_depth: Max depth per tree.
        learning_rate: Shrinkage rate applied to each tree's contribution.
        n_bootstrap: Bootstrap resamples for the backtest metrics' CI.
        confidence_level: Confidence level for that CI, e.g. 0.95 for 95%.
        seed: Random seed for the bootstrap, for reproducibility.
        date_col: Name of the date column in the CSV.
        value_col: Name of the value column in the CSV.
    """
    df = load_series(csv_path, date_col, value_col)
    return _fit_gradient_boosted_trees(
        df,
        holdout_size=holdout_size,
        lags=lags,
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        n_bootstrap=n_bootstrap,
        confidence_level=confidence_level,
        seed=seed,
    )


@mcp.tool()
def diebold_mariano_test(
    actuals: list,
    predicted_a: list,
    predicted_b: list,
    model_a_name: str = "Model A",
    model_b_name: str = "Model B",
    loss: str = "squared",
    n_lags: Optional[int] = None,
) -> dict:
    """Diebold-Mariano-style test (Diebold & Mariano, 1995) for whether
    two models' forecasts on the SAME holdout have significantly
    different accuracy -- gives "compare candidates honestly" actual
    statistical backing instead of eyeballing two error numbers. Without
    this, "SARIMA's MAPE is 4.8% vs seasonal_naive's 5.0%" has no way to
    tell a real difference from noise in a holdout that's often only
    ~30 points.

    Pass `actuals` (the holdout_actuals from either fit_* result being
    compared -- both must have used the SAME csv_path/holdout_size) and
    each model's holdout_predicted. A negative mean_loss_differential
    favors model A; positive favors model B.

    Uses a Newey-West (Bartlett-kernel) HAC-robust variance estimate of
    the mean loss differential, with n_lags defaulting to the standard
    Newey & West (1994) automatic rule -- appropriate for a genuinely
    multi-step backtest (fit_ets/fit_sarima), where later-horizon errors
    are typically autocorrelated with earlier ones. Pass n_lags=0 when
    BOTH models being compared are one-step-ahead backtests (e.g. two
    fit_gradient_boosted_trees runs), where that autocorrelation isn't
    expected. Uses a Student's t reference distribution (df = n - 1),
    a standard conservative choice for small holdout sizes.

    IMPORTANT: comparing fit_ets/fit_sarima (genuinely multi-step)
    against fit_gradient_boosted_trees (one-step-ahead) with this test
    tells you whether the error numbers differ significantly -- it does
    NOT resolve the apples-to-oranges evaluation-setting mismatch
    documented on fit_gradient_boosted_trees itself. Carry that caveat
    forward regardless of what this test says.

    Args:
        actuals: The real holdout values (same for both models).
        predicted_a: Model A's predictions on the same holdout.
        predicted_b: Model B's predictions on the same holdout.
        model_a_name: Label for model A in the result, e.g. "SARIMA".
        model_b_name: Label for model B in the result, e.g. "seasonal_naive".
        loss: "squared" (default) or "absolute".
        n_lags: Newey-West truncation lag. Defaults to the automatic
            Newey & West (1994) rule; pass 0 to assume independent errors.
    """
    return _diebold_mariano_test(
        actuals,
        predicted_a,
        predicted_b,
        model_a_name=model_a_name,
        model_b_name=model_b_name,
        loss=loss,
        n_lags=n_lags,
    )


def main():
    """Entry point for the `ts-forecaster-server` console script."""
    mcp.run()  # defaults to stdio transport, which is what OpenClaw expects


if __name__ == "__main__":
    main()
