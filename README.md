# TradingAgentsCrypto

Crypto-first refactor of the original `TradingAgents` framework.

Original project: [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)  
Original paper: [TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138)

## Current Flow

The active runtime is now:

`Analyst Team -> Research Team -> Decision Team -> Risk Management -> Execution Team`

Current agents:

- `Market Structure Analyst`
- `Volume Flow Analyst`
- `Funding & OI Analyst`
- `News Analyst`
- `Tokenomics & On-Chain Analyst`
- `Bull Researcher`
- `Bear Researcher`
- `Research Manager`
- `Setup Classifier`
- `Decision Engine`
- `Trade Risk Analyst`
- `Portfolio Risk Analyst`
- `Execution Team`

This is a research and decision-support pipeline. It does not place live orders.

## What Changed

- The repo is crypto-first, not stock-first.
- Default market focus is perpetual crypto pairs such as `BTC-PERP`.
- Runtime supports `1h`, `4h`, and `1d`.
- Profiles bootstrap from `tradingagents.defaults.json` and persist in SQLite.
- Full state logs, report sections, complete markdown reports, and reflection memory persist in SQLite.
- SQLite retention is capped automatically so old history does not grow forever.
- A new FastAPI web UI can start runs and monitor progress from SQLite.
- The web UI now includes single-asset monitoring loops with a minimum 10-minute interval and a maximum of 5 active pairs.
- The old portfolio-manager stage was removed from the active flow.
- Default provider order is Hyperliquid-first for market and derivatives data.

## Project Layout

- `cli`
  Terminal UI, prompts, runtime progress, reporting, and profile loading.
- `tradingagents/services`
  Shared analysis runtime used by both CLI and web.
- `tradingagents/agents`
  Analyst, research, decision, risk, and execution agents.
- `tradingagents/dataflows/providers`
  Market, derivatives, tokenomics, and news providers.
- `tradingagents/graph`
  Workflow graph, propagation, routing, and reflection.
- `tradingagents/storage`
  SQLite repository layer.
- `tradingagents/web`
  FastAPI routes, HTML templates, and monitoring UI.

## Installation

```powershell
cd D:\sui\alphbot\project\TradingAgents

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -e .
```

If you use the default `codex_exec` provider:

```powershell
codex login
```

## CLI Usage

Run the CLI:

```powershell
python -m cli.main
```

If installed as a package:

```powershell
tradingagents
```

Show options:

```powershell
python -m cli.main --help
```

Available options:

- `--profile PATH`
  Use a different JSON bootstrap profile key.
- `--edit-profile`
  Re-open the interactive prompts and save the result to SQLite for that profile key.

Important behavior:

- One run analyzes one `asset_symbol`.
- There is no batch watchlist runtime in the current repo.
- `tradingagents.defaults.json` is the bootstrap/default contract.
- The saved active profile lives in SQLite and is keyed by profile path.

## Web Usage

Start the web app:

```powershell
tradingagents-web
```

If the command is not found, reinstall the package in your active venv:

```powershell
pip install -e .
```

Or with Uvicorn directly:

```powershell
uvicorn tradingagents.web.app:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/runs
```

What the web UI does now:

- starts a new analysis run without using the CLI
- saves the submitted selections back to the default SQLite profile when requested
- creates monitoring loops for single pairs
- enforces `max 5` active loops and `min 10 minutes` per pair
- schedules loop runs in-process and persists loop state in SQLite
- shows recent runs from SQLite
- shows configured monitoring loops, their next run time, and active run links
- shows per-team and per-agent status from persisted run progress
- shows messages, tool calls, report sections, complete markdown report, and final state log

What it does not do yet:

- multi-user auth
- websocket updates for the loops page (the run detail view is live via WebSocket; `/loops` is manual refresh)
- multi-instance safe loop coordination; the scheduler is still in-process for a single web instance

## Default Profile

Repo bootstrap file:

```text
tradingagents.defaults.json
```

Current default content:

```json
{
  "asset_symbol": "BTC-PERP",
  "timeframe": "1h",
  "analysis_date": "now",
  "storage_retention_days": 7,
  "storage_max_runs_per_asset_timeframe": 240,
  "storage_max_reflection_entries_per_memory": 300,
  "output_language": "English",
  "analysts": [
    "market_structure_analyst",
    "volume_flow_analyst",
    "funding_oi_analyst",
    "news_analyst",
    "tokenomics_onchain_analyst"
  ],
  "research_depth": 1,
  "llm_provider": "codex_exec",
  "backend_url": null,
  "shallow_thinker": "gpt-5.4-mini",
  "deep_thinker": "gpt-5.4",
  "google_thinking_level": null,
  "openai_reasoning_effort": null,
  "anthropic_effort": null
}
```

Field notes:

- `asset_symbol`: single symbol or pair such as `BTC-PERP`, `ETH-PERP`, `SOL/USDT`
- `timeframe`: `1h`, `4h`, or `1d`
- `analysis_date`: `now`, `today`, `current`, `YYYY-MM-DD HH:MM`, or `YYYY-MM-DD`
- `storage_retention_days`: prune completed run history older than this many days
- `storage_max_runs_per_asset_timeframe`: keep at most this many completed runs per `asset_symbol + timeframe`
- `storage_max_reflection_entries_per_memory`: keep at most this many reflection-memory entries per memory bucket
- `research_depth`: valid values are `1`, `3`, `5`
- `analysts`: saved aliases normalize to internal keys `market`, `volume_flow`, `funding_oi`, `news`, `tokenomics`

## Timeframe Behavior

- `1h`: normalize to the current hour
- `4h`: normalize to the current 4-hour bucket
- `1d`: normalize to the current day

Provider behavior:

- market and derivatives tools follow the selected timeframe
- news lookback follows the selected timeframe
- tokenomics and on-chain context may be slower-moving than the chart timeframe, and the agent should say when data is unavailable

## Loop Scheduling

- Monitoring loops are fixed to hourly minute slots `00`, `12`, `24`, `36`, `48`
- active pair #1 gets `:00`, pair #2 gets `:12`, pair #3 gets `:24`, pair #4 gets `:36`, pair #5 gets `:48`
- slot assignment follows the active loop order in SQLite
- paused loops lose their slot until resumed
- loop definitions can be paused and resumed from the web UI; delete is intentionally disabled

## Storage

Default SQLite database:

```text
~/.tradingagents/tradingagents.sqlite3
```

Override with:

```powershell
$env:TRADINGAGENTS_DB_PATH="D:\path\to\tradingagents.sqlite3"
```

SQLite stores:

- saved profiles
- analysis runs
- monitoring loop definitions
- live run progress snapshots
- message logs
- tool-call logs
- report sections
- full state logs
- complete markdown reports
- reflection memory

Retention behavior:

- completed runs older than `storage_retention_days` are pruned automatically
- completed runs are also capped by `storage_max_runs_per_asset_timeframe`
- reflection memory is capped by `storage_max_reflection_entries_per_memory`
- active/running loop runs are not pruned while still active

## Default Data Providers

Current defaults from `tradingagents/default_config.py`:

- `market_data`: `hyperliquid,binance`
- `technical_indicators`: `hyperliquid,binance`
- `derivatives_data`: `hyperliquid,binance`
- `tokenomics_data`: `coingecko`
- `news_data`: `google_news,coingecko`

## Suggested Hyperliquid Symbols

If you want a small default perpetual universe, these are the cleanest starting symbols for this repo:

- `BTC-PERP`
- `ETH-PERP`
- `HYPE-PERP`
- `SOL-PERP`
- `XRP-PERP`

## Python Example

```python
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = DEFAULT_CONFIG.copy()
config["timeframe"] = "4h"
config["quick_think_llm"] = "gpt-5.4-mini"
config["deep_think_llm"] = "gpt-5.4"

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("BTC-PERP", "2026-04-14 12:00")

print(decision)
```

## Current Limits

- This repo is not production auto-trading infrastructure.
- There is no built-in live order execution path.
- Higher `research_depth` increases latency and model cost.
- `Tokenomics & On-Chain Analyst` is only as good as the available provider data; it should not invent missing on-chain context.

## Notes

- This repo is crypto-focused.
- Output is not financial advice.
- Profitability is not guaranteed.
