"""
server.py — FastMCP server for the Layer 5 retrain-cycle tools.

Closes the loop after ts-monitor recommends retrain_now: gives the agent a
place to record what's actually deployed (so there's something to compare
against later) and a deterministic answer to "is a freshly retrained
candidate actually better enough to be worth redeploying."

This layer never calls ts-deploy itself and never redeploys anything on
its own -- it produces a recommendation for a human to act on. See
skills/ts-retrain/SKILL.md for the full workflow.

Run over stdio (how OpenClaw will launch it), after `pip install -e .`:
    ts-retrain-server
    # or: python -m agentic_ts_toolkit.retrain.server
"""

from typing import Optional

from fastmcp import FastMCP

from .retrain_tools import (
    record_deployment as _record_deployment,
    load_deployment_manifest as _load_deployment_manifest,
    compare_candidate_to_deployed as _compare_candidate_to_deployed,
)

mcp = FastMCP("ts-retrain")


@mcp.tool()
def record_deployment(
    csv_path: str,
    model: str,
    params: dict,
    backtest_metrics: dict,
    horizon: int,
    manifest_path: Optional[str] = None,
) -> dict:
    """Persist a record of what's currently deployed: model type, params,
    its backtest metrics from ts-forecaster, and the forecast horizon.
    Call this right after an actual, human-confirmed ts-deploy call -- not
    after every exploratory forecast_* call. Overwrites any existing
    manifest for this series; it always reflects the single
    currently-deployed model, not a history.

    Args:
        csv_path: Path to the series CSV this model was deployed against.
        model: Model name/type, e.g. "SARIMA", "ETS (Holt-Winters)".
        params: The params dict the deployed forecast_* tool used.
        backtest_metrics: The backtest_metrics dict from the matching
            ts-forecaster fit_* call that justified deploying this model.
        horizon: The forecast horizon (in steps) that was deployed.
        manifest_path: Where to write the manifest. Defaults to
            deployment_manifest.json next to csv_path.
    """
    return _record_deployment(
        csv_path,
        model=model,
        params=params,
        backtest_metrics=backtest_metrics,
        horizon=horizon,
        manifest_path=manifest_path,
    )


@mcp.tool()
def load_deployment_manifest(csv_path: str, manifest_path: Optional[str] = None) -> dict:
    """Read back what's currently recorded as deployed for this series.
    Returns an error dict (not an exception) if nothing has been recorded
    yet -- that's an expected state early in a series' lifecycle, not a bug.

    Args:
        csv_path: Path to the series CSV.
        manifest_path: Where to look. Defaults to deployment_manifest.json
            next to csv_path.
    """
    return _load_deployment_manifest(csv_path, manifest_path=manifest_path)


@mcp.tool()
def compare_candidate_to_deployed(
    candidate_metrics: dict,
    deployed_metrics: dict,
    metric_name: str = "mape_pct",
    improvement_threshold_pct: float = 10.0,
) -> dict:
    """Deterministic decision: does a freshly backtested candidate model
    beat what's currently deployed by enough to be worth redeploying? This
    is intentionally rule-based, not left to model judgment -- same reason
    ts-monitor__recommend_retraining is deterministic. Requires a relative
    improvement of at least improvement_threshold_pct before recommending
    a swap, to avoid churn from noise-level differences.

    Args:
        candidate_metrics: backtest_metrics dict from a fresh
            ts-forecaster fit_* call on the updated series.
        deployed_metrics: backtest_metrics dict from
            load_deployment_manifest's "backtest_metrics" field.
        metric_name: Which key to compare; must be present and
            lower-is-better in both dicts (e.g. "mape_pct", "mae", "rmse").
        improvement_threshold_pct: Minimum relative improvement (%) the
            candidate needs over the deployed model before this
            recommends redeploying.
    """
    return _compare_candidate_to_deployed(
        candidate_metrics,
        deployed_metrics,
        metric_name=metric_name,
        improvement_threshold_pct=improvement_threshold_pct,
    )


def main():
    """Entry point for the `ts-retrain-server` console script."""
    mcp.run()  # defaults to stdio transport, which is what OpenClaw expects


if __name__ == "__main__":
    main()
