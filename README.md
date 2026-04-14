# TradingAgentsCrypto

Crypto-specialized fork/refactor of the original `TradingAgents` framework.

Original from: [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)  
Original README reference: [README.md](https://github.com/TauricResearch/TradingAgents/blob/main/README.md)

## What This Repo Is

`TradingAgentsCrypto` keeps the multi-agent trading workflow from the original project, but the active runtime has been refactored for crypto analysis instead of equity analysis.

Current crypto flow:
- `Market Analyst`: spot trend, volatility, structure, and derivatives context
- `Sentiment Analyst`: narrative strength, crowding, and attention
- `News Analyst`: crypto-specific catalysts and market news
- `Tokenomics Analyst`: supply, dilution, FDV, market cap, and structural risk
- `Bull Researcher` / `Bear Researcher`: investment debate
- `Trader`: execution-oriented proposal
- `Risk Management` + `Portfolio Manager`: final decision

## What Changed From The Original

- Stock/company-specific modules were removed from the active codepath.
- State now uses `asset_symbol` instead of company/ticker semantics.
- Fundamentals were replaced with `tokenomics`.
- Data routing is crypto-first:
  - `binance` for OHLCV and derivatives metrics
  - `coingecko` for tokenomics and trending assets
  - `google_news` for crypto news aggregation
- Default LLM provider is `codex_exec`.

## Project Layout

- `D:\sui\alphbot\project\TradingAgents\tradingagents\graph`
  Graph orchestration, routing, reflection, propagation.
- `D:\sui\alphbot\project\TradingAgents\tradingagents\agents`
  Analysts, researchers, trader, risk, and portfolio manager agents.
- `D:\sui\alphbot\project\TradingAgents\tradingagents\dataflows\providers`
  Crypto market/tokenomics/news providers.
- `D:\sui\alphbot\project\TradingAgents\cli`
  Interactive CLI entrypoint and terminal UI.

## Installation

```powershell
cd D:\sui\alphbot\project\TradingAgents

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -e .
```

If you use the default `codex_exec` provider, log in first:

```powershell
codex login
```

## Run

CLI:

```powershell
python -m cli.main analyze
```

Installed command:

```powershell
tradingagents analyze
```

You will be prompted for:
- crypto asset symbol or pair, for example `BTCUSDT`, `ETHUSDT`, `SOL/USDT`
- analysis date
- analyst set
- LLM provider and model

To avoid re-entering the same settings every run, the CLI now auto-loads `tradingagents.defaults.json` from the repo root. By default it uses the saved profile directly. The sample file ships with:

- `analysis_date: "today"` so each run automatically uses the current local date
- reusable analyst/model/provider defaults

If you want to change the saved defaults interactively:

```powershell
python -m cli.main --edit-profile
```

If you want to use a different JSON profile path:

```powershell
python -m cli.main --profile D:\path\to\my-profile.json
```

## Python Example

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5.4-mini"
config["quick_think_llm"] = "gpt-5.4-mini"

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("BTCUSDT", "2024-05-10")

print(decision)
```

See `D:\sui\alphbot\project\TradingAgents\main.py` for the local example script.

## Default Data Providers

Current defaults in `D:\sui\alphbot\project\TradingAgents\tradingagents\default_config.py`:

- `market_data`: `binance`
- `technical_indicators`: `binance`
- `tokenomics_data`: `coingecko`
- `derivatives_data`: `binance`
- `news_data`: `google_news,coingecko`

## Notes

- This repo is now oriented to crypto research and decision support, not stock analysis.
- It is still a research framework, not production trading infrastructure.
- It does not guarantee profitability and is not financial advice.

## Credits

- Original project: [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
- Original paper: [TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138)
