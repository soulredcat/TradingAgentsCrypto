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
- The old portfolio-manager stage was removed from the active flow.
- Default provider order is Hyperliquid-first for market and derivatives data.

## Project Layout

- `cli`
  Terminal UI, prompts, runtime progress, reporting, and profile loading.
- `tradingagents/agents`
  Analyst, research, decision, risk, and execution agents.
- `tradingagents/dataflows/providers`
  Market, derivatives, tokenomics, and news providers.
- `tradingagents/graph`
  Workflow graph, propagation, routing, and reflection.
- `tradingagents/storage`
  SQLite repository layer.

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
- message logs
- tool-call logs
- report sections
- full state logs
- complete markdown reports
- reflection memory

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
