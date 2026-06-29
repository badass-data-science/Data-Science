# Graph Report - forex  (2026-06-28)

## Corpus Check
- Corpus is ~3,414 words - fits in a single context window. You may not need a graph.

## Summary
- 131 nodes · 221 edges · 12 communities (6 shown, 6 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 32 edges (avg confidence: 0.75)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Market Timezone & Core ETL|Market Timezone & Core ETL]]
- [[_COMMUNITY_Candlestick Data Models & Tests|Candlestick Data Models & Tests]]
- [[_COMMUNITY_Candlestick ETL Engine|Candlestick ETL Engine]]
- [[_COMMUNITY_Forward Fill Transformer|Forward Fill Transformer]]
- [[_COMMUNITY_Prefect Pipeline Flows|Prefect Pipeline Flows]]
- [[_COMMUNITY_Forward Fill (Checkpoint)|Forward Fill (Checkpoint)]]
- [[_COMMUNITY_Deployment & Infrastructure|Deployment & Infrastructure]]
- [[_COMMUNITY_Candlestick Pipeline (A)|Candlestick Pipeline (A)]]
- [[_COMMUNITY_Candlestick Pipeline (B)|Candlestick Pipeline (B)]]
- [[_COMMUNITY_Database Configuration|Database Configuration]]

## God Nodes (most connected - your core abstractions)
1. `CandlestickETL` - 18 edges
2. `is_market_open_at_time()` - 15 edges
3. `_at()` - 13 edges
4. `CandlestickRecord` - 12 edges
5. `ForwardFillInator` - 12 edges
6. `ForwardFillInator` - 12 edges
7. `TestMarketHours` - 12 edges
8. `TestToInfluxDict` - 11 edges
9. `CandlestickPipeline` - 9 edges
10. `CandlestickPipeline` - 9 edges

## Surprising Connections (you probably didn't know these)
- `check_market_open_task()` --calls--> `is_market_open()`  [INFERRED]
  flows/candlestick_flow.py → critical_timezone.py
- `fetch_candlestick_data()` --calls--> `CandlestickETL`  [INFERRED]
  flows/candlestick_flow.py → etl/CandlestickETL.py
- `TestCandlestickRecord` --uses--> `CandlestickRecord`  [INFERRED]
  tests/test_models.py → etl/models.py
- `TestToInfluxDict` --uses--> `CandlestickRecord`  [INFERRED]
  tests/test_models.py → etl/models.py
- `CandlestickETL` --uses--> `CandlestickRecord`  [INFERRED]
  etl/CandlestickETL.py → etl/models.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Prefect-Orchestrated Forex ETL Pipeline Deployment** — forex_how_to_start_forex_pipeline_candlestick_flow, forex_how_to_start_forex_pipeline_forward_fill_flow, forex_how_to_start_forex_pipeline_prefect_server, forex_how_to_start_forex_pipeline_cron_schedule [EXTRACTED 1.00]
- **Forex ETL Credential Chain** — forex_how_to_start_forex_pipeline_oanda_config, forex_how_to_start_forex_pipeline_aws_secrets_manager, forex_how_to_start_forex_pipeline_influxdb [EXTRACTED 1.00]

## Communities (12 total, 6 thin omitted)

### Community 0 - "Market Timezone & Core ETL"
Cohesion: 0.16
Nodes (6): is_market_open(), is_market_open_at_time(), datetime, _at(), TestMarketHours, TestTimezoneObject

### Community 1 - "Candlestick Data Models & Tests"
Cohesion: 0.17
Nodes (4): BaseModel, CandlestickRecord, TestCandlestickRecord, TestToInfluxDict

### Community 4 - "Prefect Pipeline Flows"
Cohesion: 0.24
Nodes (11): candlestick_flow(), check_market_open_task(), fetch_candlestick_data(), insert_to_influxdb(), _make_ifc(), Prefect flow: fetch Oanda candlesticks → InfluxDB.  Deploy:     python -m forex., forward_fill_flow(), forward_fill_task() (+3 more)

### Community 6 - "Deployment & Infrastructure"
Cohesion: 0.31
Nodes (10): AWS Secrets Manager, candlestick_flow, check_market_open_task, CronSchedule (prefect.schedules), How to Start Forex Pipeline, forward_fill_flow, InfluxDB, Oanda Config JSON (+2 more)

## Knowledge Gaps
- **3 isolated node(s):** `Oanda Config JSON`, `InfluxDB`, `Prefect Server`
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CandlestickETL` connect `Candlestick ETL Engine` to `Market Timezone & Core ETL`, `Candlestick Data Models & Tests`, `Prefect Pipeline Flows`, `Candlestick Pipeline (A)`, `Candlestick Pipeline (B)`?**
  _High betweenness centrality (0.349) - this node is a cross-community bridge._
- **Why does `is_market_open_at_time()` connect `Market Timezone & Core ETL` to `Forward Fill (Checkpoint)`?**
  _High betweenness centrality (0.206) - this node is a cross-community bridge._
- **Why does `CandlestickRecord` connect `Candlestick Data Models & Tests` to `Candlestick ETL Engine`?**
  _High betweenness centrality (0.198) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `CandlestickETL` (e.g. with `CandlestickRecord` and `fetch_candlestick_data()`) actually correct?**
  _`CandlestickETL` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `is_market_open_at_time()` (e.g. with `.compute_df_all_time_diff_market_open()` and `.test_friday_16_is_open()`) actually correct?**
  _`is_market_open_at_time()` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `CandlestickRecord` (e.g. with `CandlestickETL` and `.make_the_InfluxDB_dict()`) actually correct?**
  _`CandlestickRecord` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `# TODO: replace with an explicit holiday calendar.`, `Prefect flow: fetch Oanda candlesticks → InfluxDB.  Deploy:     python -m forex.`, `Prefect flow: forward-fill stored candlestick gaps → InfluxDB.  Deploy:     pyth` to the rest of the system?**
  _6 weakly-connected nodes found - possible documentation gaps or missing edges._