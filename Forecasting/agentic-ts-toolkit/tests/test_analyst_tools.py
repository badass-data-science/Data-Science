import numpy as np
import pandas as pd
import pytest

pytest.importorskip("statsmodels")

from agentic_ts_toolkit.data_prep import generate_synthetic_series
from agentic_ts_toolkit.analyst.analysis_tools import (
    basic_stats,
    check_stationarity,
    seasonal_decomposition_summary,
    acf_pacf_summary,
    detect_anomalies_zscore,
)


@pytest.fixture
def sample_df():
    return generate_synthetic_series(n_days=200)


def test_basic_stats(sample_df):
    result = basic_stats(sample_df)
    assert result["n_observations"] == 200
    assert result["n_missing_values"] == 0


def test_check_stationarity_returns_expected_keys(sample_df):
    result = check_stationarity(sample_df)
    assert "adf_statistic" in result
    assert "p_value" in result
    assert isinstance(result["is_likely_stationary"], bool)
    assert "mean_reversion_lambda" in result
    assert "mean_reversion_half_life_periods" in result


def test_check_stationarity_reports_finite_half_life_for_mean_reverting_series():
    rng = np.random.default_rng(0)
    n = 500
    y = np.zeros(n)
    for t in range(1, n):
        y[t] = 0.7 * y[t - 1] + rng.normal(0, 1.0)  # AR(1), strongly mean-reverting
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=n, freq="D"), "value": y})

    result = check_stationarity(df)
    assert result["mean_reversion_lambda"] < 0
    assert result["mean_reversion_half_life_periods"] is not None
    assert result["mean_reversion_half_life_periods"] > 0


def test_check_stationarity_reports_weak_reversion_for_a_pure_random_walk():
    rng = np.random.default_rng(3)
    n = 500
    y = np.cumsum(rng.normal(0, 1.0, size=n))  # random walk: no true mean reversion
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=n, freq="D"), "value": y})

    result = check_stationarity(df)
    # Don't assert mean_reversion_lambda >= 0 here: under a true unit root, the
    # OLS lambda estimate is well-known to skew slightly negative in finite
    # samples (the reason ADF needs its own non-standard critical values
    # rather than a plain t-test) -- it's not reliably non-negative even when
    # there's truly no reversion. What should hold instead: the formal ADF
    # verdict says non-stationary, and if a half-life comes out at all, it's
    # long enough to be practically meaningless, not a fast, useful reversion.
    assert result["is_likely_stationary"] is False
    assert (
        result["mean_reversion_half_life_periods"] is None
        or result["mean_reversion_half_life_periods"] > n / 2
    )


def test_seasonal_decomposition_summary(sample_df):
    result = seasonal_decomposition_summary(sample_df, period=7)
    assert 0 <= result["trend_strength"] <= 1
    assert 0 <= result["seasonal_strength"] <= 1


def test_acf_pacf_summary(sample_df):
    result = acf_pacf_summary(sample_df, n_lags=14)
    assert result["n_lags_checked"] == 14


def test_detect_anomalies_zscore(sample_df):
    result = detect_anomalies_zscore(sample_df, z_threshold=3.0)
    assert "n_anomalies_flagged" in result
