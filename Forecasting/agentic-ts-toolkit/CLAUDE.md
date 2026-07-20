# agentic-ts-toolkit

Five layers of agentic time series tooling. Each layer is a FastMCP server
(typed tools) plus a companion OpenClaw skill (markdown playbook telling an
agent how to sequence those tools and what to report). Built to be driven
by OpenClaw + an LLM agent (developed against GLM-5.2 on Ollama Cloud, but
nothing is model-specific).

- `analyst`    -> `ts-analyst`    : explore a series, recommend an approach. No fitting.
- `forecaster` -> `ts-forecaster` : fit + backtest candidate models on a held-out window.
- `deploy`     -> `ts-deploy`     : retrain the chosen model on full data, forecast forward.
- `monitor`    -> `ts-monitor`    : compare deployed forecast vs. reality, detect drift, recommend retraining.
- `retrain`    -> `ts-retrain`    : on retrain_now, re-run analyst+forecaster and decide deterministically whether the new candidate beats what's deployed. Never redeploys itself.

Full architecture/setup is in README.md — don't duplicate it here.

## Commands

```bash
pip install -e ".[all,dev]"    # everything, including test deps
pytest                          # run the suite
ts-analyst-server                # run a layer's MCP server standalone (Ctrl+C to stop)
python -m build                 # build sdist/wheel for publishing
```

Per-layer installs: `.[analyst]`, `.[forecaster]`, `.[deploy]`, `.[monitor]`, `.[retrain]` if you don't want every dependency.

## Non-obvious conventions

- **One shared `data_prep.py`** at the package root (`agentic_ts_toolkit.data_prep`). Every subpackage imports it — never re-add a per-layer copy.
- **Within a subpackage, tools return plain functions taking a DataFrame; `server.py` wraps them as `@mcp.tool()` and does the CSV loading.** Keep that split — it's what makes the tool logic unit-testable without spinning up MCP (see `tests/`, which import the tools modules directly, not through `server.py`).
- **`recommend_retraining` in `monitor_tools.py` is deliberately deterministic/rule-based**, not an LLM judgment call — that's intentional, not a missed opportunity to "let the agent decide." Keep new decision-style tools (accept/reject, threshold-based verdicts) rule-based for the same reason: reproducibility given the same inputs. `retrain_tools.py`'s `compare_candidate_to_deployed` follows the same rule.
- **Every `SKILL.md` references its tools by their MCP-qualified name** (`ts-analyst__basic_stats`, etc.), not by file path — these are OpenClaw skills, not exec-based scripts. If you add a tool, update the matching `SKILL.md`'s tool list too.
- **Tests use `pytest.importorskip("statsmodels")` / `"sklearn"`** in the layers that need them (`analyst`, `forecaster`, `deploy`), so `pip install -e .` (core deps only) doesn't break the whole suite. `monitor`, `retrain`, and `data_prep` tests have no such guard — keep it that way, they're meant to run everywhere (neither needs statsmodels/sklearn).
- **`ts-retrain` is the one place in the toolkit with durable state** — `record_deployment`/`load_deployment_manifest` read and write a JSON manifest (`deployment_manifest.json` by default, next to the series CSV; see `_manifest_path_for` in `retrain_tools.py`). Every other tool in every other layer is a pure function of its explicit inputs — don't add more file-based state elsewhere without a similarly strong reason.
- **`ts-retrain` never calls `ts-deploy` and never redeploys anything on its own** — it stops after `compare_candidate_to_deployed` and waits for human confirmation (see its `SKILL.md`, Step 4). Don't wire it to auto-redeploy without that being an explicit, separately-scoped change — see "Known modeling caveats" note below on why this boundary matters.

## Known modeling caveats (intentional, not bugs)

- `forecaster/model_tools.py`'s gradient-boosted-trees backtest is **one-step-ahead** (true lagged values); `deploy/forecast_tools.py`'s gradient-boosted-trees forecast is **recursive** (predictions feed back in as lags). These are not directly comparable to each other or to ETS/SARIMA's genuine multi-step forecasts — both modules' docstrings and return values flag this explicitly. Don't "fix" this asymmetry without understanding why it exists.
- `monitor/monitor_tools.py`'s `detect_data_drift` cannot distinguish an ongoing trend/seasonal transition from a genuine regime change — confirmed empirically that it flags `drift_detected=True` on trending synthetic data with zero injected anomaly. This is by design (a coarse, fast check); read `interpretation`, don't treat the boolean as ground truth.
- `retrain/retrain_tools.py`'s `compare_candidate_to_deployed` requires a relative improvement above `improvement_threshold_pct` (default 10%) before recommending a swap, not just any improvement — this is deliberate, to avoid redeploying (and resetting the monitoring baseline) over noise-level metric differences between two similar fits.

## Where things live

- `src/agentic_ts_toolkit/skills/` — the five `SKILL.md` files, bundled as package data via `skills_dir()` in `__init__.py`.
- `openclaw.config.snippet.jsonc` — reference config for wiring all five servers + a model into OpenClaw.
