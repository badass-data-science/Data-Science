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
- `retrain`    -> `ts-retrain`    : on retrain_now, re-run analyst+forecaster and decide deterministically whether the new candidate beats what's deployed; redeploys only through the gated `execute_redeploy(confirmed=True)` tool, either human-approved (default) or via an explicitly authorized autonomous mode.

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
- **Tests use `pytest.importorskip("statsmodels")` / `"sklearn"`** in the layers that need them (`analyst`, `forecaster`, `deploy`), so `pip install -e .` (core deps only) doesn't break the whole suite. `monitor` and `data_prep` tests have no such guard — keep it that way, they're meant to run everywhere. `retrain` is mostly in that camp too (`record_deployment`/`load_deployment_manifest`/`compare_candidate_to_deployed` need nothing beyond core), but `test_retrain_tools.py`'s one test of `execute_redeploy`'s real dispatch path uses a per-test (not module-level) `importorskip`, since `execute_redeploy` alone needs the `deploy` extra — don't move that guard to the top of the file, it would skip tests that don't need it.
- **`ts-retrain` is the one place in the toolkit with durable state** — `record_deployment`/`load_deployment_manifest` read and write a JSON manifest (`deployment_manifest.json` by default, next to the series CSV; see `_manifest_path_for` in `retrain_tools.py`). Every other tool in every other layer is a pure function of its explicit inputs — don't add more file-based state elsewhere without a similarly strong reason.
- **`ts-retrain` only ever changes a deployment through `execute_redeploy`, which refuses to run without `confirmed=True`** (no default performs the action). Two paths reach that confirmation, both documented in `SKILL.md`: human approval in-conversation (default), or an explicitly authorized autonomous mode where the skill calls `execute_redeploy(confirmed=True)` itself. The authorization check for autonomous mode is a prose contract enforced by the skill's instructions, not something the code validates — `execute_redeploy` itself doesn't know or care which path led to `confirmed=True`. Don't weaken the skill's "default to human mode when ambiguous" language, and don't add a code path that sets `confirmed=True` by default anywhere.
  - Human-confirmed example: after `ts-retrain` reports `should_redeploy: true` and stops, the user says *"Go ahead and redeploy the candidate you just recommended"* — that follow-up is what authorizes the `execute_redeploy(..., confirmed=True)` call.
  - Autonomous-mode example: authorization is scoped per series, stated explicitly, e.g. *"For the `daily_demand.csv` series specifically, you're authorized to redeploy automatically whenever ts-retrain finds a candidate that beats the current deployment — no need to ask me first. Everything else still needs my confirmation as usual."* Absent wording this explicit and this scoped, treat autonomous mode as not authorized.
- **Both `SARIMAX(...)` call sites (`forecaster/model_tools.py::fit_sarima`, `deploy/forecast_tools.py::forecast_sarima`) pass a single-column DataFrame (`df[["value"]]`), not a Series (`df["value"]`).** This isn't stylistic -- statsmodels does an in-place `ndarray.shape=` reshape internally, but only for 1-D endog, and NumPy 2.5+ deprecated in-place shape mutation, so a Series triggers a `DeprecationWarning` on every fit. A single-column DataFrame is already 2-D, so statsmodels skips that code path -- verified identical AIC/BIC, residuals, and forecast values/shapes either way. If you add another `SARIMAX(...)` call site, pass a DataFrame the same way.

## Known modeling caveats (intentional, not bugs)

- `forecaster/model_tools.py`'s gradient-boosted-trees backtest is **one-step-ahead** (true lagged values); `deploy/forecast_tools.py`'s gradient-boosted-trees forecast is **recursive** (predictions feed back in as lags). These are not directly comparable to each other or to ETS/SARIMA's genuine multi-step forecasts — both modules' docstrings and return values flag this explicitly. Don't "fix" this asymmetry without understanding why it exists.
- `monitor/monitor_tools.py`'s `detect_data_drift` cannot distinguish an ongoing trend/seasonal transition from a genuine regime change — confirmed empirically that it flags `drift_detected=True` on trending synthetic data with zero injected anomaly. This is by design (a coarse, fast check); read `interpretation`, don't treat the boolean as ground truth.
- `retrain/retrain_tools.py`'s `compare_candidate_to_deployed` requires a relative improvement above `improvement_threshold_pct` (default 10%) before recommending a swap, not just any improvement — this is deliberate, to avoid redeploying (and resetting the monitoring baseline) over noise-level metric differences between two similar fits.
- `retrain/retrain_tools.py`'s `execute_redeploy` imports `deploy/forecast_tools.py` as a whole module, so it needs the `deploy` extra (statsmodels + scikit-learn) installed regardless of `model_type` — even `model_type="naive"` triggers the same module-level import. The `retrain` extra itself stays dependency-free on purpose, since the diagnostic tools don't need it; only `execute_redeploy` does.
- `analyst/analysis_tools.py`'s `check_stationarity` runs ADF AND KPSS together and reports an effect size for each. **Field names changed when KPSS was added**: the ADF fields were renamed from `p_value`/`is_likely_stationary` to `adf_p_value`/`adf_is_likely_stationary`, so two different tests' results in the same dict wouldn't be ambiguous. If you're referencing this tool's output anywhere (a `SKILL.md`, a test, an integration), use the prefixed names.
  - ADF's effect size (`mean_reversion_lambda`, `mean_reversion_half_life_periods`) comes from an independent OLS fit of `delta_y_t = lambda*y_{t-1} + mu + epsilon_t` (not derived from `adfuller`'s own internals, so it stays interpretable on its own and isn't coupled to ADF's autolag choice). **Don't assume `mean_reversion_lambda >= 0` under a true unit root** — the OLS estimate is well-known to skew slightly negative in finite samples even with zero true reversion (exactly why ADF needs its own non-standard critical values rather than a plain t-test); this bit a test during development (see `test_check_stationarity_reports_weak_reversion_for_a_pure_random_walk` in `tests/test_analyst_tools.py`, which asserts on `adf_is_likely_stationary`/half-life magnitude instead of the sign of lambda for that reason).
  - KPSS's effect size (`kpss_effect_size`) is the KPSS statistic as a multiple of its own 5% critical value, computed from values `kpss()` already returns (no re-implementation of its Newey-West long-run variance estimator). This exists specifically because KPSS's own p-value is coarse: `statsmodels` interpolates it from just four lookup-table points and clips it at the table's edges, so p-values of 0.01 or 0.10 can mean "barely past the boundary" or "wildly past it" with no way to tell from the p-value alone. `_kpss_effect_size` deliberately suppresses the `InterpolationWarning` `kpss()` raises at those clipped boundaries — that's not silencing a problem, the effect size *is* the more informative answer to the exact thing the warning is pointing at.
  - ADF and KPSS have opposite null hypotheses (ADF: unit root; KPSS: stationary) — `_combined_stationarity_interpretation` encodes the standard four-way readout (both agree stationary, both agree non-stationary, or either disagreement direction, each with its own guidance e.g. "try `kpss_regression='ct'`"). Keep new stationarity-adjacent tools consistent with this framing rather than reporting ADF and KPSS as two independent, unrelated facts.
- `analyst/analysis_tools.py`'s `acf_pacf_summary` and `detect_anomalies_zscore` both report an effect size for anything they flag, sorted strongest/most-extreme first (not chronologically) before capping the list for brevity. **This changed both fields' shape, not just added new ones**: `significant_acf_lags` went from a bare list of lag integers to a list of `{lag, acf, effect_size}` dicts; `detect_anomalies_zscore` replaced `anomaly_dates` (date strings only) with `anomalies` (`{date, value, z_score}` dicts) plus a new `max_abs_z_score` summary field. Same rationale as the ADF/KPSS effect sizes above: a bare "flagged" boolean throws away magnitude the function already computed internally to make that decision — don't add a new flagging tool that collapses a computed score down to a boolean without also surfacing the score.

## Where things live

- `src/agentic_ts_toolkit/skills/` — the five `SKILL.md` files, bundled as package data via `skills_dir()` in `__init__.py`.
- `openclaw.config.snippet.jsonc` — reference config for wiring all five servers + a model into OpenClaw.
