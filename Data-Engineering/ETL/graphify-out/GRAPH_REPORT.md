# Graph Report - forex  (2026-06-29)

## Corpus Check
- 4 files · ~3,317 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 121 nodes · 192 edges · 13 communities (7 shown, 6 thin omitted)
- Extraction: 85% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 28 edges (avg confidence: 0.77)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Market Hours & Core Files|Market Hours & Core Files]]
- [[_COMMUNITY_Docs, Flows & Deployment Config|Docs, Flows & Deployment Config]]
- [[_COMMUNITY_Forward Fill Pipeline|Forward Fill Pipeline]]
- [[_COMMUNITY_Candlestick ETL Class|Candlestick ETL Class]]
- [[_COMMUNITY_Pydantic Data Model & Tests|Pydantic Data Model & Tests]]
- [[_COMMUNITY_InfluxDB Dict Tests|InfluxDB Dict Tests]]
- [[_COMMUNITY_Prefect Candlestick Flow|Prefect Candlestick Flow]]
- [[_COMMUNITY_Candlestick Pipeline Orchestration|Candlestick Pipeline Orchestration]]
- [[_COMMUNITY_Prefect Forward Fill Flow|Prefect Forward Fill Flow]]
- [[_COMMUNITY_Database Config|Database Config]]
- [[_COMMUNITY_serve.py Deployment Script|serve.py Deployment Script]]

## God Nodes (most connected - your core abstractions)
1. `CandlestickETL` - 15 edges
2. `is_market_open_at_time()` - 14 edges
3. `_at()` - 13 edges
4. `CandlestickRecord` - 13 edges
5. `ForwardFillInator` - 12 edges
6. `TestMarketHours` - 12 edges
7. `TestToInfluxDict` - 11 edges
8. `CandlestickPipeline` - 10 edges
9. `CandlestickPipeline` - 7 edges
10. `TestCandlestickRecord` - 6 edges

## Surprising Connections (you probably didn't know these)
- `TestToInfluxDict` --uses--> `CandlestickRecord`  [INFERRED]
  tests/test_models.py → etl/models.py
- `candlestick_batch_flow (All Major Pairs)` --references--> `CandlestickPipeline`  [INFERRED]
  how_to_start_forex_pipeline.md → README.md
- `candlestick_flow (One-off Single Pair)` --references--> `CandlestickPipeline`  [INFERRED]
  how_to_start_forex_pipeline.md → README.md
- `TestCandlestickRecord` --uses--> `CandlestickRecord`  [INFERRED]
  tests/test_models.py → etl/models.py
- `Prerequisites (Installation and Auth)` --references--> `InfluxDB`  [INFERRED]
  how_to_start_forex_pipeline.md → README.md

## Import Cycles
- None detected.

## Communities (13 total, 6 thin omitted)

### Community 0 - "Market Hours & Core Files"
Cohesion: 0.17
Nodes (6): is_market_open(), is_market_open_at_time(), datetime, _at(), TestMarketHours, TestTimezoneObject

### Community 1 - "Docs, Flows & Deployment Config"
Cohesion: 0.13
Nodes (19): candlestick_batch_flow (All Major Pairs), candlestick_flow (One-off Single Pair), check_market_open_task, CandlestickRecord Data Model (Schema Constants), forward_fill_flow, Prerequisites (Installation and Auth), serve.py (Scheduled Deployments), Pipeline Architecture (+11 more)

### Community 4 - "Pydantic Data Model & Tests"
Cohesion: 0.29
Nodes (3): BaseModel, CandlestickRecord, TestCandlestickRecord

### Community 6 - "Prefect Candlestick Flow"
Cohesion: 0.39
Nodes (8): candlestick_batch_flow(), candlestick_flow(), check_market_open_task(), fetch_candlestick_data(), insert_to_influxdb(), _make_ifc(), Prefect flows: fetch Oanda candlesticks → InfluxDB.  Single pair (ad-hoc):     p, Run candlestick_flow for each instrument sequentially.

### Community 8 - "Prefect Forward Fill Flow"
Cohesion: 0.47
Nodes (5): forward_fill_flow(), forward_fill_task(), _make_ifc(), Prefect flow: forward-fill stored candlestick gaps → InfluxDB.  Deploy:     pyth, InfluxDbTool

## Knowledge Gaps
- **6 isolated node(s):** `Oanda REST API`, `candlestick_flow (One-off Single Pair)`, `forward_fill_flow`, `serve.py (Scheduled Deployments)`, `check_market_open_task` (+1 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CandlestickRecord` connect `Pydantic Data Model & Tests` to `Candlestick ETL Class`, `InfluxDB Dict Tests`, `Candlestick Pipeline Orchestration`?**
  _High betweenness centrality (0.134) - this node is a cross-community bridge._
- **Why does `CandlestickETL` connect `Candlestick ETL Class` to `Market Hours & Core Files`, `Pydantic Data Model & Tests`, `Candlestick Pipeline Orchestration`?**
  _High betweenness centrality (0.121) - this node is a cross-community bridge._
- **Why does `CandlestickPipeline` connect `Candlestick Pipeline Orchestration` to `Market Hours & Core Files`, `Candlestick ETL Class`, `Pydantic Data Model & Tests`?**
  _High betweenness centrality (0.088) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `CandlestickETL` (e.g. with `CandlestickRecord` and `CandlestickPipeline`) actually correct?**
  _`CandlestickETL` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `is_market_open_at_time()` (e.g. with `.test_friday_16_is_open()` and `.test_friday_17_is_closed()`) actually correct?**
  _`is_market_open_at_time()` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `CandlestickRecord` (e.g. with `CandlestickETL` and `.make_the_InfluxDB_dict()`) actually correct?**
  _`CandlestickRecord` has 10 INFERRED edges - model-reasoned connections that need verification._
- **What connects `# TODO: replace with an explicit holiday calendar.`, `Prefect flow: forward-fill stored candlestick gaps → InfluxDB.  Deploy:     pyth`, `Prefect flows: fetch Oanda candlesticks → InfluxDB.  Single pair (ad-hoc):     p` to the rest of the system?**
  _12 weakly-connected nodes found - possible documentation gaps or missing edges._