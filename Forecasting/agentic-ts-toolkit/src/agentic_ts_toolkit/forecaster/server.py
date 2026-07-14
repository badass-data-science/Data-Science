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
    date_col: str = "date",
    value_col: str = "value",
) -> dict:
    """Fit two trivial baselines every real candidate model should beat:
    a flat naive forecast (repeat the last training value) and a seasonal
    naive forecast (repeat the value from `seasonal_period` steps back).
    Always run this first -- it's the floor any fancier model must clear.

    Args:
        csv_path: Path to a CSV with a date column and a value column.
        holdout_size: Number of most-recent observations to backtest against.
        seasonal_period: Assumed seasonal cycle length for seasonal_naive.
        date_col: Name of the date column in the CSV.
        value_col: Name of the value column in the CSV.
    """
    df = load_series(csv_path, date_col, value_col)
    return _fit_naive_baselines(df, holdout_size=holdout_size, seasonal_period=seasonal_period)


@mcp.tool()
def fit_ets(
    csv_path: str,
    holdout_size: int = 30,
    seasonal_period: int = 7,
    trend: str = "add",
    seasonal: str = "add",
    damped_trend: bool = False,
    date_col: str = "date",
    value_col: str = "value",
) -> dict:
    """Fit Holt-Winters exponential smoothing (ETS) on the training split,
    forecast the holdout window, and return backtest error metrics plus
    AIC and a residual autocorrelation diagnostic (Ljung-Box).

    Args:
        csv_path: Path to a CSV with a date column and a value column.
        holdout_size: Number of most-recent observations to backtest against.
        seasonal_period: Seasonal cycle length (e.g. 7 for weekly in daily data).
        trend: "add", "mul", or None.
        seasonal: "add", "mul", or None.
        damped_trend: Whether to damp the trend component.
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
    )


@mcp.tool()
def fit_sarima(
    csv_path: str,
    holdout_size: int = 30,
    order: Optional[list] = None,
    seasonal_order: Optional[list] = None,
    date_col: str = "date",
    value_col: str = "value",
) -> dict:
    """Fit a SARIMA model on the training split, forecast the holdout
    window, and return backtest error metrics plus AIC/BIC and a residual
    autocorrelation diagnostic (Ljung-Box).

    Args:
        csv_path: Path to a CSV with a date column and a value column.
        holdout_size: Number of most-recent observations to backtest against.
        order: [p, d, q] non-seasonal ARIMA order. Defaults to [1, 1, 1].
        seasonal_order: [P, D, Q, s] seasonal order. Defaults to [1, 1, 1, 7].
        date_col: Name of the date column in the CSV.
        value_col: Name of the value column in the CSV.
    """
    df = load_series(csv_path, date_col, value_col)
    return _fit_sarima(df, holdout_size=holdout_size, order=order, seasonal_order=seasonal_order)


@mcp.tool()
def fit_gradient_boosted_trees(
    csv_path: str,
    holdout_size: int = 30,
    lags: Optional[list] = None,
    n_estimators: int = 200,
    max_depth: int = 3,
    learning_rate: float = 0.05,
    date_col: str = "date",
    value_col: str = "value",
) -> dict:
    """Fit gradient-boosted trees on lag + calendar features and backtest
    on the holdout window. NOTE: this is evaluated one-step-ahead using
    true lagged values, not a recursive multi-step forecast -- it is an
    easier evaluation setting than fit_ets/fit_sarima above, and the tool
    result flags this explicitly. Don't compare its error numbers directly
    against ETS/SARIMA without accounting for that.

    Args:
        csv_path: Path to a CSV with a date column and a value column.
        holdout_size: Number of most-recent observations to backtest against.
        lags: List of lag steps to use as features. Defaults to [1, 7, 14].
        n_estimators: Number of boosting stages.
        max_depth: Max depth per tree.
        learning_rate: Shrinkage rate applied to each tree's contribution.
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
    )


def main():
    """Entry point for the `ts-forecaster-server` console script."""
    mcp.run()  # defaults to stdio transport, which is what OpenClaw expects


if __name__ == "__main__":
    main()
