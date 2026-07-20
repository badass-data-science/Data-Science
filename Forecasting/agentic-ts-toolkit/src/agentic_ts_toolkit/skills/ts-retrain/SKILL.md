---
name: ts-retrain
description: Close the loop after ts-monitor recommends retrain_now -- re-run analyst/forecaster, decide deterministically whether a fresh candidate beats what's deployed, and stop for human confirmation before redeploying.
---

# Time Series Retrain Cycle

You are acting on a `retrain_now` (or `investigate`) verdict from
`ts-monitor__recommend_retraining`. Your job is to find out whether
retraining actually produces something worth deploying -- not to redeploy
automatically. This skill NEVER calls `ts-deploy` itself; it stops with a
recommendation and waits for a human to confirm before anything gets
redeployed.

## Prerequisites

You need:
1. The `retrain_now` (or similar) verdict and reasoning from `ts-monitor`,
   so you can explain why this cycle is running.
2. The UPDATED series CSV (the same one `ts-monitor` just checked).
3. A deployment manifest for this series -- call
   `ts-retrain__load_deployment_manifest` first. If it returns an error
   (nothing recorded yet), say so plainly and stop: without a recorded
   deployed-model baseline, there's nothing to compare a new candidate
   against.

## Available tools

- `ts-retrain__load_deployment_manifest` — read what's currently recorded
  as deployed (model, params, backtest metrics, horizon) for this series.
- `ts-retrain__compare_candidate_to_deployed` — DELIBERATELY deterministic
  decision: does a freshly backtested candidate beat the deployed model by
  more than a threshold (default 10% relative improvement)? Call this
  rather than eyeballing whether the new numbers "look better."
- `ts-retrain__record_deployment` — writes the manifest. Only call this
  yourself AFTER the user has confirmed a redeploy AND you've actually run
  `ts-deploy` with the new settings -- never call it speculatively, and
  never as part of this skill's own automatic flow.

## Step 1 — Load the current deployment record

Call `load_deployment_manifest`. If it errors, stop and report that
there's no baseline to retrain against; suggest the user run `ts-deploy`
normally first (and then `record_deployment`) before a retrain cycle can
be evaluated against anything.

## Step 2 — Re-run analyst and forecaster on the updated series

Re-invoke the `ts-analyst` skill on the current CSV -- the series'
characteristics (stationarity, seasonality, anomalies) may have shifted
since this last ran, which can change what approach makes sense now, not
just what parameters to use.

Then re-invoke the `ts-forecaster` skill: fit and backtest candidates on
the updated series, and pick a best candidate using the same judgment you
would normally apply (real error metrics + residual diagnostics, not just
the lowest error number). This is still your call to make -- this skill
does not automate model selection, only the final "is it worth swapping"
gate in Step 3.

## Step 3 — Get the deterministic redeploy verdict

Call `compare_candidate_to_deployed` with:
- `candidate_metrics`: your chosen candidate's `backtest_metrics` from Step 2
- `deployed_metrics`: the `backtest_metrics` field from Step 1's manifest
- `metric_name`: the default `mape_pct` is usually fine; use `mae` or
  `rmse` instead only if you have a specific reason (e.g. MAPE was
  unreliable due to near-zero values in this series)

Do not substitute your own read of "does this look better" for this
tool's output -- if its verdict surprises you given what you saw in Step
2, say so as a caveat in your report, but still report what it actually
returned.

## Step 4 — Write your report and stop

- **Why this cycle ran**: the `ts-monitor` verdict that triggered it.
- **What changed in Steps 1-2**: anything notable from re-running
  `ts-analyst` (e.g. a newly detected anomaly, a shifted seasonal
  strength), and which candidate you selected in `ts-forecaster` and why.
- **The verdict**: `compare_candidate_to_deployed`'s `should_redeploy` and
  its `reasoning`, stated plainly.
- **What happens next**:
  - If `should_redeploy` is true: tell the user exactly what you'd deploy
    (model + params) and ask them to confirm. Only after they say go,
    run the `ts-deploy` skill with those settings, then call
    `ts-retrain__record_deployment` to update the manifest. Do not do
    this in the same turn without confirmation.
  - If `should_redeploy` is false: say the current deployment stays as
    is, and note that retraining alone didn't resolve whatever
    `ts-monitor` flagged -- worth a closer human look at whether this
    needs a different model family or feature set, not just fresh
    parameters of the same one.
