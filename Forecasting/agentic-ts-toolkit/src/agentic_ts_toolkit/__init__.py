"""
agentic_ts_toolkit

Four layers of agentic time series tooling, each exposed as a FastMCP
server, plus companion OpenClaw skills bundled alongside them:

- agentic_ts_toolkit.analyst    -> ts-analyst    (explore & recommend an approach)
- agentic_ts_toolkit.forecaster -> ts-forecaster (fit & backtest candidate models)
- agentic_ts_toolkit.deploy     -> ts-deploy     (retrain on full data, forecast forward)
- agentic_ts_toolkit.monitor    -> ts-monitor    (check deployed forecasts, recommend retraining)

See each subpackage's server.py for its MCP tools, and skills_dir() below
for the bundled SKILL.md playbooks.
"""

from importlib.resources import files as _files

__version__ = "0.1.0"


def skills_dir():
    """Return the path to the bundled OpenClaw skill directories
    (ts-analyst/, ts-forecaster/, ts-deploy/, ts-monitor/), so they can be
    copied into an OpenClaw workspace after `pip install`:

        cp -r "$(python -c 'import agentic_ts_toolkit as t; print(t.skills_dir())')"/* \\
            ~/.openclaw/workspace/skills/
    """
    return _files("agentic_ts_toolkit") / "skills"
