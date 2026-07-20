# agentic-ts-toolkit

Five layers of agentic time series tooling, packaged as a normal
installable Python project. Each layer is a FastMCP server (typed tools)
plus a companion OpenClaw skill (the reasoning workflow around those
tools), bundled together so the whole thing installs and updates as one
package.

- **Layer 1 — `ts-analyst`**: explore a series (stationarity, seasonality,
  anomalies) and recommend a forecasting approach with reasoning.
- **Layer 2 — `ts-forecaster`**: fit candidate models against a common
  held-out window, backtest them, and recommend one with reasoning
  grounded in real error metrics and residual diagnostics.
- **Layer 3 — `ts-deploy`**: retrain the chosen model on the full series
  and produce a real forecast beyond the end of the data, with prediction
  intervals where available.
- **Layer 4 — `ts-monitor`**: once real observations exist, check whether
  the deployed forecast is still tracking reality, detect data drift, and
  recommend whether to retrain.
- **Layer 5 — `ts-retrain`**: when `ts-monitor` says `retrain_now`,
  re-run Layers 1-2 on the updated series and deterministically decide
  whether the freshly backtested candidate beats what's currently
  deployed by enough to be worth redeploying. Never redeploys on its
  own -- it stops for human confirmation.

## Project layout

```
agentic-ts-toolkit/
├── pyproject.toml
├── LICENSE
├── README.md
├── .gitignore
├── openclaw.config.snippet.jsonc
├── src/
│   └── agentic_ts_toolkit/
│       ├── __init__.py            # version + skills_dir() helper
│       ├── data_prep.py           # shared: synthetic data + CSV loader (used by all 4 layers)
│       ├── analyst/
│       │   ├── __init__.py
│       │   ├── analysis_tools.py  # Layer 1 diagnostic functions
│       │   └── server.py          # FastMCP server: ts-analyst
│       ├── forecaster/
│       │   ├── __init__.py
│       │   ├── model_tools.py     # Layer 2 fit/backtest functions
│       │   └── server.py          # FastMCP server: ts-forecaster
│       ├── deploy/
│       │   ├── __init__.py
│       │   ├── forecast_tools.py  # Layer 3 retrain/forecast functions
│       │   └── server.py          # FastMCP server: ts-deploy
│       ├── monitor/
│       │   ├── __init__.py
│       │   ├── monitor_tools.py   # Layer 4 comparison/drift/retrain-decision functions
│       │   └── server.py          # FastMCP server: ts-monitor
│       ├── retrain/
│       │   ├── __init__.py
│       │   ├── retrain_tools.py   # Layer 5 deployment-manifest + redeploy-decision functions
│       │   └── server.py          # FastMCP server: ts-retrain
│       └── skills/                # bundled as package data -- see skills_dir()
│           ├── ts-analyst/SKILL.md
│           ├── ts-forecaster/SKILL.md
│           ├── ts-deploy/SKILL.md
│           ├── ts-monitor/SKILL.md
│           └── ts-retrain/SKILL.md
└── tests/
    ├── test_data_prep.py
    ├── test_analyst_tools.py
    ├── test_forecaster_tools.py
    ├── test_deploy_tools.py
    ├── test_monitor_tools.py
    └── test_retrain_tools.py
```

## What changed from the earlier ad-hoc layout

- **One `data_prep.py`, not four copies.** Every layer previously had its
  own duplicate for self-containment as a standalone MCP server folder;
  now they all import `agentic_ts_toolkit.data_prep`.
- **Real packaging metadata.** `pyproject.toml` declares dependencies,
  optional extras per layer, and console-script entry points
  (`ts-analyst-server`, `ts-forecaster-server`, `ts-deploy-server`,
  `ts-monitor-server`) so OpenClaw's config can reference an installed
  command instead of an absolute path to a `.py` file.
- **Skills are bundled package data.** `agentic_ts_toolkit.skills_dir()`
  returns the installed path to the four `SKILL.md` files, so you can
  install this package and copy the skills into an OpenClaw workspace
  without needing the original source tree around.
- **A real test suite**, using `pytest.importorskip` for the tests that
  need `statsmodels`/`scikit-learn`, so `pip install -e .` (core deps
  only) still lets you run the tests that don't need them.

## Setup

### 1. Install
```bash
python -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -e ".[all]"       # every layer's dependencies
# or install only what you need:
#   pip install -e ".[analyst]"                 # Layer 1 only
#   pip install -e ".[forecaster,deploy]"       # Layers 2+3
#   pip install -e ".[monitor]"                 # Layer 4 only
#   pip install -e ".[retrain]"                 # Layer 5 only (no extra deps beyond core)
#   pip install -e ".[dev]"                     # + pytest, for running tests
```

### 2. Run the test suite
```bash
pip install -e ".[all,dev]"
pytest
```

### 3. Sanity-check each server runs standalone
```bash
ts-analyst-server      # Ctrl+C to stop; no output/crash = good
ts-forecaster-server
ts-deploy-server
ts-monitor-server
ts-retrain-server
```

### 4. Register with OpenClaw
Merge `openclaw.config.snippet.jsonc` into `~/.openclaw/openclaw.json` --
no path editing needed if the console scripts are on `PATH` (true inside
the venv you installed into). Then:
```bash
openclaw mcp status --verbose
openclaw mcp doctor --probe
openclaw mcp tools ts-analyst
```

### 5. Install the bundled skills
```bash
mkdir -p ~/.openclaw/workspace/skills
cp -r "$(python -c 'import agentic_ts_toolkit as t; print(t.skills_dir())')"/* \
    ~/.openclaw/workspace/skills/
```
Start a new OpenClaw session afterward (skills are snapshotted at session
start).

### 6. Point OpenClaw at your model of choice
This project was developed against GLM-5.2 on Ollama Cloud:
```bash
export OLLAMA_API_KEY="<your-ollama-cloud-api-key>"
openclaw models list --provider ollama-cloud
openclaw models set ollama-cloud/glm-5.2:cloud
```
Nothing about the package is tied to that specific model -- swap
`agents.defaults.model.primary` in the config for whatever you're running.

## Run it

Full pipeline, one message to your OpenClaw agent:

> Use ts-analyst to explore a synthetic time series, then use
> ts-forecaster to fit and backtest candidate models informed by what you
> found, then use ts-deploy to produce a 30-day forecast with the
> best-performing model and settings.

Once time has passed and the CSV has real new observations:

> Use ts-monitor to check whether that forecast is holding up against
> what actually happened, and tell me if I should retrain.

Right after that first real `ts-deploy` call, record what got deployed so
Layer 5 has a baseline to compare against later:

> Use ts-retrain to record that this model and its backtest metrics are
> now deployed.

If `ts-monitor` comes back with `retrain_now`:

> Use ts-retrain to re-run analyst and forecaster on the updated series
> and tell me whether the new candidate is actually worth redeploying.

## Publishing this to PyPI

This layout is ready for it as-is:
```bash
pip install build twine
python -m build                      # produces dist/*.whl and dist/*.tar.gz
twine upload --repository testpypi dist/*    # try TestPyPI first
twine upload dist/*                          # then the real thing
```
Before actually publishing, you'll want to:
- pick a real package name (check it's free on PyPI first)
- fill in real author info and a real project URL in `pyproject.toml`
- bump `version` for each release
- decide whether `agentic-ts-toolkit` is the name you want, since PyPI
  names are first-come and effectively permanent once claimed

## Things worth knowing about specific tools (carried over from earlier layers)

- **`ts-forecaster`'s gradient-boosted-trees backtest is one-step-ahead**
  (uses true lagged values), while ETS/SARIMA get scored on a genuine
  multi-step forecast -- not directly comparable without accounting for that.
- **`ts-deploy`'s gradient-boosted-trees forecast is recursive** (each
  prediction feeds back in as a lag for the next step), so errors can
  compound over a long horizon -- a risk that didn't apply to Layer 2's
  evaluation of the same model type.
- **`ts-monitor`'s drift detector can't distinguish trend/seasonality from
  a genuine regime change** -- confirmed directly: running it on this
  project's synthetic data (which has a real upward trend) flags
  `drift_detected=True` even with no injected anomaly, purely from trend
  continuation. Read the `interpretation` field rather than treating the
  boolean as an automatic alarm.
- **`ts-monitor__recommend_retraining` is deliberately deterministic
  rather than left to model judgment** -- "should we retrain" is the kind
  of decision worth being reproducible given the same inputs.
- **`ts-retrain` never calls `ts-deploy` and never redeploys anything
  itself** -- it re-runs Layers 1-2, then hands the resulting candidate to
  `ts-retrain__compare_candidate_to_deployed` (deterministic, same reason
  as `recommend_retraining` above) and stops. Redeploying is a separate,
  human-confirmed step.
- **`ts-retrain`'s deployment manifest is the only piece of durable state
  in the whole toolkit** -- a JSON file (`deployment_manifest.json` by
  default, written next to the series CSV) recording what model/params/
  backtest metrics are currently deployed. Nothing else persists between
  calls; every other tool is a pure function of its inputs.

## Next steps

With Layer 5 in place, a natural follow-up is an *optional* autonomous
mode: given explicit opt-in (e.g. a flag or a standing instruction), skip
the human-confirmation pause in Step 4 of `ts-retrain`'s workflow and let
a `should_redeploy: true` verdict chain straight into `ts-deploy` and
`record_deployment`. Deliberately not the default -- redeploying a live
forecast unattended is a meaningfully different risk than the read-only
diagnostics every other layer performs.
