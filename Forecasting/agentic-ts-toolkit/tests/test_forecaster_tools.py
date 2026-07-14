import pytest

pytest.importorskip("statsmodels")
pytest.importorskip("sklearn")

from agentic_ts_toolkit.data_prep import generate_synthetic_series
from agentic_ts_toolkit.forecaster.model_tools import (
    train_test_split,
    fit_naive_baselines,
    fit_ets,
    fit_sarima,
    fit_gradient_boosted_trees,
)


@pytest.fixture
def sample_df():
    return generate_synthetic_series(n_days=300)


def test_train_test_split_sizes(sample_df):
    train, test = train_test_split(sample_df, holdout_size=30)
    assert len(train) == 270
    assert len(test) == 30


def test_fit_naive_baselines_seasonal_beats_flat_on_seasonal_data(sample_df):
    result = fit_naive_baselines(sample_df, holdout_size=30, seasonal_period=7)
    assert result["seasonal_naive"]["mae"] < result["naive"]["mae"]


def test_fit_ets_returns_metrics_and_aic(sample_df):
    result = fit_ets(sample_df, holdout_size=30, seasonal_period=7)
    assert "aic" in result
    assert "mae" in result["backtest_metrics"]


def test_fit_sarima_returns_metrics_and_aic_bic(sample_df):
    result = fit_sarima(sample_df, holdout_size=30, order=[1, 1, 1], seasonal_order=[1, 1, 1, 7])
    assert "aic" in result and "bic" in result


def test_fit_gradient_boosted_trees_flags_evaluation_caveat(sample_df):
    result = fit_gradient_boosted_trees(sample_df, holdout_size=30)
    assert "evaluation_caveat" in result
    assert "feature_importances" in result
