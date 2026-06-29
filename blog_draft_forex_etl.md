# A Time-Series Database for Forex Data Engineering
## How our heroine built a production-grade OHLCV pipeline using InfluxDB and Prefect

By Badass Data Science

---

Our heroine—a mild-mannered data scientist by day—has a side interest in quantitative finance. She wants to build systematic trading strategies, but systematic trading strategies require data. Reliable, clean, continuously updated data. And so, before she could do anything interesting with forex prices, she had to solve a more fundamental problem: how do you store and maintain a decade's worth of candlestick data in a way that makes it fast to query, easy to update, and honest about what's in it?

This post describes the pipeline she built to do that.

---

## Why Forex, and Why Candlesticks

Our heroine sources her data from Oanda, a retail forex broker that exposes a REST API for historical and streaming price data. Oanda provides candlestick (OHLCV) data: for each time interval, the open, high, low, and close prices for both the bid and ask sides of the market, plus volume.

A candlestick for EUR/USD at hourly granularity looks roughly like this in Oanda's API response:

```json
{
  "time": "1700000000",
  "complete": true,
  "volume": 1842,
  "bid": { "o": "1.09001", "h": "1.09187", "l": "1.08994", "c": "1.09142" },
  "ask": { "o": "1.09015", "h": "1.09201", "l": "1.09008", "c": "1.09156" }
}
```

The `complete` flag matters: an incomplete candlestick means the interval hasn't closed yet. Including incomplete candles in a training dataset would introduce look-ahead bias. The pipeline filters them out.

---

## The Database Decision: Why InfluxDB

Our heroine considered a relational database first. PostgreSQL can store time-series data. It will accept a row per candle, and you can index on timestamp. It works.

But it fights the data model.

Forex OHLCV data has a specific shape: it is append-only (you never update a closed candle), it is almost always queried by time range, and it has a fixed set of metadata that naturally groups rows—`instrument` (EUR/USD, GBP/JPY, etc.) and `granularity` (M15, H1, D). In relational terms these are filter columns, not join columns. Every interesting query starts with "give me all EUR/USD H1 candles between these two timestamps."

InfluxDB is built for exactly this. It organizes data into **measurements** (think: table), **tags** (indexed metadata—`instrument` and `granularity` here), and **fields** (the actual values—bid/ask OHLCV, volume). Its query language, Flux, expresses time-range scans and tag filters in a few readable lines:

```flux
from(bucket: "forex")
  |> range(start: 2024-01-01T00:00:00Z)
  |> filter(fn: (r) => r.instrument == "EUR/USD")
  |> filter(fn: (r) => r.granularity == "H1")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
```

The same query in SQL would require a WHERE clause, a timestamp index hint, and if you want the bid and ask fields as columns rather than rows, a pivot or a set of self-joins. InfluxDB makes the common case simple.

There is also a practical consideration: InfluxDB has built-in retention policies, downsampling tasks, and a time-series aware data model that handles the `max(timestamp)` query—"what is the most recent candle already stored for this instrument?"—extremely efficiently. Our heroine uses this query on every pipeline run to determine where to resume ingestion. In a relational database this would require a table scan or a carefully maintained index. In InfluxDB it is a first-class operation.

---

## Pipeline Architecture

The pipeline has three moving parts: the Oanda API client, a validation layer, and the InfluxDB write path. Prefect coordinates them. Here is the shape of it:

```
Oanda REST API
      ↓
CandlestickETL.fit()
      ↓  (raw dict → structured record)
CandlestickRecord  [Pydantic validation]
      ↓  (to_influx_dict())
InfluxDbTool.insert_dictionary_list()
      ↓
InfluxDB
```

Each layer has a single responsibility. The ETL class fetches and normalises raw API responses. The Pydantic model validates the shape of each record and produces the dict structure that InfluxDB expects. The InfluxDB tool handles the write. Nothing crosses those boundaries.

---

## Fetching Data: CandlestickETL

The Oanda API returns up to 5,000 candles per request. Our heroine's `CandlestickETL` class walks backward through time in 5,000-candle windows until it reaches the most recent timestamp already stored in InfluxDB, then writes only the new records. On first run it fetches from 2009 (the beginning of available Oanda data). On subsequent runs it resumes from where it left off.

A `tenacity` retry decorator handles transient network failures cleanly:

```python
@retry(
    stop=stop_after_attempt(5),
    wait=wait_fixed(2),
    retry=retry_if_exception_type(requests.RequestException),
    reraise=True,
)
def _fetch_from_api(self, url: str) -> dict:
    r = requests.get(url, headers=self.headers)
    r.raise_for_status()
    return r.json()
```

Five attempts, two seconds between each, re-raise on final failure so Prefect can record the task as failed rather than hanging.

---

## Validation: CandlestickRecord

Before anything touches the database, each candle passes through a Pydantic model:

```python
class CandlestickRecord(BaseModel):
    instrument: str
    granularity: str
    volume: int
    complete: bool
    bid_open: float
    bid_high: float
    bid_low: float
    bid_close: float
    ask_open: float
    ask_high: float
    ask_low: float
    ask_close: float
    timestamp: int

    TAGS: ClassVar[frozenset[str]] = frozenset({'instrument', 'granularity'})
    MEASUREMENT: ClassVar[str] = 'candlestick'

    def to_influx_dict(self) -> dict:
        data = self.model_dump()
        result = {
            'measurement': self.MEASUREMENT,
            'tags': {},
            'fields': {},
            'time': data.pop('timestamp'),
        }
        for key, value in data.items():
            if key in self.TAGS:
                result['tags'][key] = value
            else:
                result['fields'][key] = value
        return result
```

`CandlestickRecord` is the only place in the entire pipeline where the schema is enforced. If the Oanda API ever returns a malformed response, or if a code change accidentally drops a field, the `ValidationError` is raised here—at the write boundary—rather than written silently to the database as a null. The `to_influx_dict()` method then produces exactly the structure `InfluxDbTool` expects: a measurement name, a tag dict, a field dict, and a timestamp.

This separation is visible in the knowledge graph of our heroine's codebase. The graph clusters `CandlestickRecord` and its test suite into their own community, separate from the InfluxDB tool community—because `CandlestickRecord` never touches the database client. It only produces a dict. The client lives elsewhere.

**[IMAGE: graphify community graph, Communities 4 (CandlestickETL Core), 17 (Candlestick Pydantic Model & Tests), and 35 (InfluxDB Tool) highlighted and annotated. Caption: "Three separate communities in the knowledge graph. CandlestickRecord (17) sits between the ETL core (4) and the database tool (35) but shares no edges with either — it only produces a dict."]**

---

## Secrets: The PEP 562 Pattern

The InfluxDB credentials live in AWS Secrets Manager under the key `Forex/InfluxDbPassword`. Fetching them at module import time—the naive approach—means credentials are retrieved before `main()` runs, before any argument parsing, and potentially in contexts (test runs, linting, CI) where AWS access is neither available nor desired.

Our heroine uses Python's PEP 562 module `__getattr__` to make the fetch lazy:

```python
# database_config.py
import json
import functools
from python_tools_and_shortcuts.aws.secrets_manager import get_secret

_SECRET_NAME = 'Forex/InfluxDbPassword'
_KEYS = frozenset(['INFLUXDB_URL', 'INFLUXDB_TOKEN', 'INFLUXDB_ORG', 'INFLUXDB_BUCKET'])

@functools.lru_cache(maxsize=None)
def _load_secret():
    return json.loads(get_secret(_SECRET_NAME))

def __getattr__(name):
    if name in _KEYS:
        return _load_secret()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

When any part of the codebase writes `from database_config import INFLUXDB_URL`, Python calls `__getattr__('INFLUXDB_URL')` at access time, not at import time. `_load_secret()` is decorated with `@functools.lru_cache`, so the boto3 call to Secrets Manager happens exactly once per process lifetime. Subsequent accesses return the cached result.

The `lru_cache` has a subtle implication for long-running Prefect deployments: if the Prefect worker process stays alive between flow runs, the secret is fetched once on the first run and cached forever. Credential rotation does not take effect until the worker is restarted. This is intentional—it avoids Secrets Manager rate limits and per-run latency—but worth knowing.

This pattern is largely invisible to static analysis tools, including the knowledge graph visualizer our heroine uses. The graph correctly shows `__getattr__()` calling `_load_secret()`, but shows no edge from `_load_secret()` to the `get_secret()` function in the AWS tools package. Two reasons: the secrets utility file (`secrets_manager.py`) is excluded by the graph tool's sensitive-filename heuristic, and the PEP 562 dispatch itself—module attribute access—does not look like a function call to an AST parser.

**[IMAGE: graphify subgraph showing database_config.py community (59), with __getattr__() → _load_secret() edge visible, and the absence of any outbound edge from _load_secret(). Caption: "The graph ends at _load_secret(). The boto3 → Secrets Manager hop is invisible: the utility file is excluded by the sensitive-filename filter, and PEP 562 module attribute dispatch doesn't register as a call edge in static analysis."]**

The invisibility is, in a way, the point. A design that is opaque to static analysis is also opaque to casual inspection of the codebase. Credentials that are never bound to a module-level variable, never written to `os.environ`, and never fetched until the moment they are needed are credentials that are harder to accidentally log, serialize, or expose.

---

## Orchestration: Prefect

The pipeline originally ran as a cron job calling a Python class directly. This worked, but provided no visibility into failures, no retry policy at the workflow level, and no run history. Our heroine replaced it with a Prefect flow.

The complete candlestick fetch flow is three tasks and a flow function:

```python
@task(name='check-market-open')
def check_market_open_task() -> bool:
    logger = get_run_logger()
    open_ = is_market_open()
    logger.info('Market is %s', 'open' if open_ else 'closed')
    return open_

@task(name='fetch-candlestick-data', retries=3, retry_delay_seconds=30)
def fetch_candlestick_data(config_file: str, instrument: str, granularity: str) -> list[dict]:
    ifc = _make_ifc()
    etl = CandlestickETL(instrument, granularity, config_file, ifc)
    etl.fit()
    return etl.to_influx_list

@task(name='insert-to-influxdb')
def insert_to_influxdb(records: list[dict]) -> None:
    if not records:
        return
    ifc = _make_ifc()
    ifc.insert_dictionary_list(records, ALLOWED_TAGS, ALLOWED_FIELDS, INFLUXDB_BUCKET)

@flow(name='forex-candlestick-etl', log_prints=True)
def candlestick_flow(config_file: str, instrument: str, granularity: str) -> None:
    if not check_market_open_task():
        return
    records = fetch_candlestick_data(config_file, instrument, granularity)
    insert_to_influxdb(records)
```

A few design choices worth noting:

**The market-hours gate.** Forex markets close Friday at 5pm Eastern and reopen Sunday at 5pm. The `check_market_open_task()` evaluates this and returns early if the market is closed, so the flow can be scheduled aggressively (every 15 minutes on weekdays) without making API calls during downtime.

**`_make_ifc()` is called inside tasks, not passed as a parameter.** Prefect serialises task parameters so they can be stored, retried, and displayed in the UI. `InfluxDbTool` holds a live HTTP connection; it cannot be pickled. Constructing it inside each task that needs it is the correct pattern—each task gets a fresh, serialisable call with only the credentials (fetched lazily from Secrets Manager) as its inputs.

**Retries live at two levels.** The `@retry` tenacity decorator on `_fetch_from_api()` handles transient network errors within a single task execution (five attempts, two seconds apart). The `retries=3, retry_delay_seconds=30` on the Prefect task handles failures that exhaust the tenacity budget—for example, a prolonged Oanda outage. Two layers, two timescales.

The flow's data path is fully traceable in the knowledge graph:

**[IMAGE: graphify path traversal output or annotated subgraph showing the chain: candlestick_flow() → check_market_open_task() → is_market_open() and candlestick_flow() → fetch_candlestick_data() → _make_ifc() → InfluxDbTool, and candlestick_flow() → insert_to_influxdb() → _make_ifc() → InfluxDbTool. Caption: "The complete data path as the knowledge graph sees it. Both the fetch and insert tasks construct InfluxDbTool independently via _make_ifc(), which is why the graph shows two separate edges from different tasks to the same InfluxDbTool node."]**

---

## The Forward Fill

Forex markets do not produce a candle for every interval. If no trades occur during a 15-minute window, Oanda returns nothing for that window. Machine learning models do not enjoy gaps in their input sequences.

`ForwardFillInator` addresses this. It pulls the stored candlestick data from InfluxDB, constructs a complete time grid for the instrument's trading hours (excluding weekends and the Friday-close to Sunday-open gap), left-joins the actual data onto the grid, and forward-fills any NaN rows. The result is a gapless sequence of OHLCV records at regular intervals, suitable for feeding directly into a model.

The market-hours logic that governs the time grid is the same `is_market_open_at_time()` function used by the pipeline's market gate—a single source of truth for what counts as a trading interval, used both to decide whether to run and to decide which rows to include in the forward-filled output.

---

## What the Knowledge Graph Reveals

Our heroine uses a knowledge graph tool to visualise the architecture of her codebase. The graph clusters code into communities by structural similarity and shared dependencies. Three observations from the current graph that are easier to see in the visualisation than in the code:

**Separation of concerns is real.** The Pydantic model (`CandlestickRecord`) and its test suite cluster into their own community with no shared edges to the InfluxDB tool community. This confirms that the schema enforcement layer is genuinely decoupled from the write layer—not just by intention in the code, but by the absence of any dependency path between them.

**The Prefect flow is the glue.** In the graph, `_make_ifc()` is the node that connects the flow community to the InfluxDB tool community. It appears twice—once in the candlestick flow, once in the forward-fill flow—and both instances reference `InfluxDbTool`. Everything upstream of `_make_ifc()` is pure business logic. Everything downstream is infrastructure. The factory function is the seam.

**The secrets path has two invisible edges.** The graph shows `__getattr__()` calling `_load_secret()`, but nothing after that. The AWS Secrets Manager call is absent. This is not an error in the graph—it is a faithful representation of what static analysis can and cannot see. The PEP 562 dispatch is too dynamic for an AST parser, and the secrets utility file is excluded by the graph tool's own security filter. The gap in the graph mirrors the gap that would exist in any static security audit of the codebase.

**[IMAGE: full graphify knowledge graph (graph.html screenshot) with the forex ETL cluster annotated. Caption: "The full portfolio knowledge graph. The forex ETL pipeline occupies the lower-right cluster, connected to the rest of the portfolio through shared infrastructure (InfluxDB tools, AWS utilities, python-tools-and-shortcuts)."]**

---

## Next Steps

Our heroine's next task is to actually use this data. The pipeline is plumbing—the interesting work is what gets built on top of it. Upcoming posts will cover feature engineering on the forward-filled OHLCV sequences, the construction of a backtesting framework, and eventually the development of a systematic strategy that her mild-mannered day-job self can run quietly in the background while she does data science.

---

## AI Use Statement

The forex ETL pipeline described in this post was developed collaboratively between the author and Claude Code (Anthropic). Code review, bug fixes, and modernisation changes were a joint effort. The knowledge graph was generated using graphify. This post was written by the human author with Claude Code contributing structural suggestions during the planning phase.
