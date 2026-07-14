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
