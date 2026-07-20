"""
server.py — FastMCP server for the time series analyst tools.

Wraps the same diagnostic logic from analysis_tools.py as typed MCP tools,
so any MCP client (OpenClaw, Claude Desktop, Claude Code, etc.) can call
them with validated arguments instead of composing shell commands.

Run directly for local testing (after `pip install -e .`):
    ts-analyst-server
    # or: python -m agentic_ts_toolkit.analyst.server

Run over stdio (how OpenClaw / most MCP clients will actually launch it):
    this IS the stdio entrypoint by default — see mcp.run() at the bottom.
"""

from typing import Optional

from fastmcp import FastMCP

from .analysis_tools import (
    basic_stats as _basic_stats,
    check_stationarity as _check_stationarity,
    seasonal_decomposition_summary as _seasonal_decomposition_summary,
    acf_pacf_summary as _acf_pacf_summary,
    detect_anomalies_zscore as _detect_anomalies_zscore,
)
from agentic_ts_toolkit.data_prep import generate_synthetic_series, load_series

mcp = FastMCP("ts-analyst")


@mcp.tool()
def generate_synthetic_data(out_path: str = "/tmp/ts_data.csv", n_days: int = 730) -> dict:
    """Generate a synthetic daily time series (trend + weekly/yearly
    seasonality + noise + a few injected anomalies) and write it to CSV.
    Use this when the user hasn't provided their own data to analyze.

    Args:
        out_path: Where to write the generated CSV.
        n_days: How many daily observations to generate.
    """
    df = generate_synthetic_series(n_days=n_days)
    df.to_csv(out_path, index=False)
    return {
        "status": "ok",
        "written_to": out_path,
        "n_rows": len(df),
        "start_date": str(df["date"].min().date()),
        "end_date": str(df["date"].max().date()),
    }


@mcp.tool()
def basic_stats(csv_path: str, date_col: str = "date", value_col: str = "value") -> dict:
    """Get summary statistics for a time series CSV: length, date range,
    missing values, and mean/std/min/max of the value column.

    Args:
        csv_path: Path to a CSV with a date column and a value column.
        date_col: Name of the date column in the CSV.
        value_col: Name of the value column in the CSV.
    """
    df = load_series(csv_path, date_col, value_col)
    return _basic_stats(df)


@mcp.tool()
def check_stationarity(csv_path: str, date_col: str = "date", value_col: str = "value") -> dict:
    """Run an Augmented Dickey-Fuller test to check whether a time series
    is stationary. A p-value below 0.05 suggests the series is stationary;
    otherwise it likely has a trend or unit root and may need differencing.
    Also returns a mean-reversion effect size (mean_reversion_lambda,
    mean_reversion_half_life_periods): a series can be statistically
    stationary yet revert so slowly the half-life is impractically long
    for short-horizon forecasting, so check both, not just the p-value.

    Args:
        csv_path: Path to a CSV with a date column and a value column.
        date_col: Name of the date column in the CSV.
        value_col: Name of the value column in the CSV.
    """
    df = load_series(csv_path, date_col, value_col)
    return _check_stationarity(df)


@mcp.tool()
def seasonal_decomposition_summary(
    csv_path: str,
    period: int = 7,
    date_col: str = "date",
    value_col: str = "value",
) -> dict:
    """Decompose a time series into trend/seasonal/residual components and
    return the relative strength of the trend and seasonal components.
    Use period=7 for daily data with weekly seasonality, period=12 for
    monthly data with yearly seasonality, etc.

    Args:
        csv_path: Path to a CSV with a date column and a value column.
        period: Assumed seasonal period, in number of observations.
        date_col: Name of the date column in the CSV.
        value_col: Name of the value column in the CSV.
    """
    df = load_series(csv_path, date_col, value_col)
    return _seasonal_decomposition_summary(df, period=period)


@mcp.tool()
def acf_pacf_summary(
    csv_path: str,
    n_lags: int = 21,
    date_col: str = "date",
    value_col: str = "value",
) -> dict:
    """Get autocorrelation and partial autocorrelation values, and which
    lags are statistically significant. Useful for identifying seasonality
    period and candidate AR/MA order.

    Args:
        csv_path: Path to a CSV with a date column and a value column.
        n_lags: Number of lags to check.
        date_col: Name of the date column in the CSV.
        value_col: Name of the value column in the CSV.
    """
    df = load_series(csv_path, date_col, value_col)
    return _acf_pacf_summary(df, n_lags=n_lags)


@mcp.tool()
def detect_anomalies_zscore(
    csv_path: str,
    z_threshold: float = 3.0,
    date_col: str = "date",
    value_col: str = "value",
) -> dict:
    """Flag observations that deviate sharply (by z_threshold standard
    deviations or more) from a local rolling mean — a simple anomaly /
    outlier detector.

    Args:
        csv_path: Path to a CSV with a date column and a value column.
        z_threshold: Number of standard deviations from the rolling mean
            to flag as anomalous.
        date_col: Name of the date column in the CSV.
        value_col: Name of the value column in the CSV.
    """
    df = load_series(csv_path, date_col, value_col)
    return _detect_anomalies_zscore(df, z_threshold=z_threshold)


def main():
    """Entry point for the `ts-analyst-server` console script."""
    mcp.run()  # defaults to stdio transport, which is what OpenClaw expects


if __name__ == "__main__":
    main()
