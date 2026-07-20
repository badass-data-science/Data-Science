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
    assert "adf_p_value" in result
    assert isinstance(result["adf_is_likely_stationary"], bool)
    assert "mean_reversion_lambda" in result
    assert "mean_reversion_half_life_periods" in result
    assert "kpss_statistic" in result
    assert "kpss_p_value" in result
    assert isinstance(result["kpss_is_likely_stationary"], bool)
    assert "kpss_effect_size" in result
    assert "kpss_critical_value_5pct" in result


def _mean_reverting_ar1_df(seed: int = 0, n: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    y = np.zeros(n)
    for t in range(1, n):
        y[t] = 0.7 * y[t - 1] + rng.normal(0, 1.0)  # AR(1), strongly mean-reverting
    return pd.DataFrame({"date": pd.date_range("2024-01-01", periods=n, freq="D"), "value": y})


def _random_walk_df(seed: int = 3, n: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    y = np.cumsum(rng.normal(0, 1.0, size=n))  # random walk: no true mean reversion
    return pd.DataFrame({"date": pd.date_range("2024-01-01", periods=n, freq="D"), "value": y})


def test_check_stationarity_reports_finite_half_life_for_mean_reverting_series():
    result = check_stationarity(_mean_reverting_ar1_df())
    assert result["mean_reversion_lambda"] < 0
    assert result["mean_reversion_half_life_periods"] is not None
    assert result["mean_reversion_half_life_periods"] > 0


def test_check_stationarity_reports_weak_reversion_for_a_pure_random_walk():
    n = 500
    result = check_stationarity(_random_walk_df(n=n))
    # Don't assert mean_reversion_lambda >= 0 here: under a true unit root, the
    # OLS lambda estimate is well-known to skew slightly negative in finite
    # samples (the reason ADF needs its own non-standard critical values
    # rather than a plain t-test) -- it's not reliably non-negative even when
    # there's truly no reversion. What should hold instead: the formal ADF
    # verdict says non-stationary, and if a half-life comes out at all, it's
    # long enough to be practically meaningless, not a fast, useful reversion.
    assert result["adf_is_likely_stationary"] is False
    assert (
        result["mean_reversion_half_life_periods"] is None
        or result["mean_reversion_half_life_periods"] > n / 2
    )


def test_check_stationarity_kpss_agrees_with_adf_on_mean_reverting_series():
    result = check_stationarity(_mean_reverting_ar1_df())
    assert result["adf_is_likely_stationary"] is True
    assert result["kpss_is_likely_stationary"] is True
    assert result["kpss_effect_size"] < 1  # comfortably under its 5% critical value
    assert "agree" in result["interpretation"]


def test_check_stationarity_kpss_agrees_with_adf_on_a_random_walk():
    result = check_stationarity(_random_walk_df())
    assert result["adf_is_likely_stationary"] is False
    assert result["kpss_is_likely_stationary"] is False
    assert result["kpss_effect_size"] > 1  # exceeds its 5% critical value
    assert "agree" in result["interpretation"]


def test_check_stationarity_kpss_effect_size_survives_p_value_clipping():
    # KPSS's own p-value is clipped at table boundaries (0.01/0.10); the
    # effect size should still distinguish magnitude past that clip.
    result = check_stationarity(_random_walk_df())
    assert result["kpss_p_value"] == 0.01  # clipped at the table's edge
    assert result["kpss_effect_size"] > 1  # but the effect size isn't clipped


def test_check_stationarity_kpss_regression_param_is_threaded_through():
    df = _mean_reverting_ar1_df()
    result_c = check_stationarity(df, kpss_regression="c")
    result_ct = check_stationarity(df, kpss_regression="ct")
    assert result_c["kpss_regression"] == "c"
    assert result_ct["kpss_regression"] == "ct"
    # "c" and "ct" fit different regressions internally, so the raw
    # statistic differs even on the same series.
    assert result_c["kpss_statistic"] != result_ct["kpss_statistic"]


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
