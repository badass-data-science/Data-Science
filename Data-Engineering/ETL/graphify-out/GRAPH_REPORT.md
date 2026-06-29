# Graph Report - forex  (2026-06-29)

## Corpus Check
- 4 files · ~2,477 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 108 nodes · 181 edges · 13 communities (7 shown, 6 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 26 edges (avg confidence: 0.74)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Market Hours & Core ETL|Market Hours & Core ETL]]
- [[_COMMUNITY_Forward Fill Pipeline|Forward Fill Pipeline]]
- [[_COMMUNITY_Candlestick ETL Class|Candlestick ETL Class]]
- [[_COMMUNITY_Pydantic Data Model & Tests|Pydantic Data Model & Tests]]
- [[_COMMUNITY_Infrastructure & Flow Config|Infrastructure & Flow Config]]
- [[_COMMUNITY_InfluxDB Dict Tests|InfluxDB Dict Tests]]
- [[_COMMUNITY_Candlestick Pipeline Orchestration|Candlestick Pipeline Orchestration]]
- [[_COMMUNITY_Prefect Candlestick Flow|Prefect Candlestick Flow]]
- [[_COMMUNITY_Prefect Forward Fill Flow|Prefect Forward Fill Flow]]
- [[_COMMUNITY_Timezone Unit Tests|Timezone Unit Tests]]
- [[_COMMUNITY_Database Config|Database Config]]

## God Nodes (most connected - your core abstractions)
1. `CandlestickETL` - 16 edges
2. `is_market_open_at_time()` - 14 edges
3. `_at()` - 13 edges
4. `CandlestickRecord` - 13 edges
5. `ForwardFillInator` - 12 edges
6. `TestMarketHours` - 12 edges
7. `TestToInfluxDict` - 11 edges
8. `CandlestickPipeline` - 10 edges
9. `candlestick_flow` - 7 edges
10. `TestCandlestickRecord` - 6 edges

## Surprising Connections (you probably didn't know these)
- `TestToInfluxDict` --uses--> `CandlestickRecord`  [INFERRED]
  tests/test_models.py → etl/models.py
- `fetch_candlestick_data()` --calls--> `CandlestickETL`  [INFERRED]
  flows/candlestick_flow.py → etl/CandlestickETL.py
- `TestCandlestickRecord` --uses--> `CandlestickRecord`  [INFERRED]
  tests/test_models.py → etl/models.py
- `CandlestickETL` --uses--> `CandlestickRecord`  [INFERRED]
  etl/CandlestickETL.py → etl/models.py
- `CandlestickPipeline` --uses--> `CandlestickETL`  [INFERRED]
  etl/pipelines/CandlestickPipeline.py → etl/CandlestickETL.py

## Import Cycles
- None detected.

## Communities (13 total, 6 thin omitted)

### Community 0 - "Market Hours & Core ETL"
Cohesion: 0.21
Nodes (5): is_market_open(), is_market_open_at_time(), datetime, _at(), TestMarketHours

### Community 3 - "Pydantic Data Model & Tests"
Cohesion: 0.29
Nodes (3): BaseModel, CandlestickRecord, TestCandlestickRecord

### Community 4 - "Infrastructure & Flow Config"
Cohesion: 0.31
Nodes (10): AWS Secrets Manager, candlestick_flow, check_market_open_task, CronSchedule (prefect.schedules), How to Start Forex Pipeline, forward_fill_flow, InfluxDB, Oanda Config JSON (+2 more)

### Community 7 - "Prefect Candlestick Flow"
Cohesion: 0.52
Nodes (6): candlestick_flow(), check_market_open_task(), fetch_candlestick_data(), insert_to_influxdb(), _make_ifc(), Prefect flow: fetch Oanda candlesticks → InfluxDB.  Deploy:     python -m forex.

### Community 8 - "Prefect Forward Fill Flow"
Cohesion: 0.47
Nodes (5): forward_fill_flow(), forward_fill_task(), _make_ifc(), Prefect flow: forward-fill stored candlestick gaps → InfluxDB.  Deploy:     pyth, InfluxDbTool

## Knowledge Gaps
- **3 isolated node(s):** `Oanda Config JSON`, `InfluxDB`, `Prefect Server`
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CandlestickETL` connect `Candlestick ETL Class` to `Market Hours & Core ETL`, `Pydantic Data Model & Tests`, `Candlestick Pipeline Orchestration`, `Prefect Candlestick Flow`?**
  _High betweenness centrality (0.299) - this node is a cross-community bridge._
- **Why does `CandlestickRecord` connect `Pydantic Data Model & Tests` to `Candlestick ETL Class`, `InfluxDB Dict Tests`, `Candlestick Pipeline Orchestration`?**
  _High betweenness centrality (0.213) - this node is a cross-community bridge._
- **Why does `fetch_candlestick_data()` connect `Prefect Candlestick Flow` to `Candlestick ETL Class`?**
  _High betweenness centrality (0.138) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `CandlestickETL` (e.g. with `CandlestickRecord` and `fetch_candlestick_data()`) actually correct?**
  _`CandlestickETL` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `is_market_open_at_time()` (e.g. with `.test_friday_16_is_open()` and `.test_friday_17_is_closed()`) actually correct?**
  _`is_market_open_at_time()` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `CandlestickRecord` (e.g. with `CandlestickETL` and `.make_the_InfluxDB_dict()`) actually correct?**
  _`CandlestickRecord` has 10 INFERRED edges - model-reasoned connections that need verification._
- **What connects `# TODO: replace with an explicit holiday calendar.`, `Prefect flow: forward-fill stored candlestick gaps → InfluxDB.  Deploy:     pyth`, `Oanda Config JSON` to the rest of the system?**
  _6 weakly-connected nodes found - possible documentation gaps or missing edges._