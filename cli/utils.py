import questionary
from typing import Iterable, List, Tuple

from rich.console import Console

from cli.models import AnalystType, get_analyst_label
from tradingagents.llm_clients.model_catalog import get_model_options
from tradingagents.time_utils import VALID_TIMEFRAMES, current_analysis_time, parse_analysis_time

console = Console()

ASSET_SYMBOL_INPUT_EXAMPLES = "Examples: BTC-PERP, ETH-PERP, HYPE-PERP, SOL/USDT"

ANALYST_ORDER = [
    (get_analyst_label(AnalystType.MARKET), AnalystType.MARKET),
    (get_analyst_label(AnalystType.VOLUME_FLOW), AnalystType.VOLUME_FLOW),
    (get_analyst_label(AnalystType.FUNDING_OI), AnalystType.FUNDING_OI),
    (get_analyst_label(AnalystType.NEWS), AnalystType.NEWS),
    (get_analyst_label(AnalystType.TOKENOMICS), AnalystType.TOKENOMICS),
]


def get_asset_symbol(default: str | None = None) -> str:
    """Prompt the user to enter a crypto asset symbol or trading pair."""
    asset_symbol = questionary.text(
        f"Enter the exact crypto asset symbol or pair to analyze ({ASSET_SYMBOL_INPUT_EXAMPLES}):",
        default=default or "",
        validate=lambda x: len(x.strip()) > 0 or "Please enter a valid crypto asset symbol.",
        style=questionary.Style(
            [
                ("text", "fg:green"),
                ("highlighted", "noinherit"),
            ]
        ),
    ).ask()

    if not asset_symbol:
        console.print("\n[red]No asset symbol provided. Exiting...[/red]")
        exit(1)

    return normalize_asset_symbol(asset_symbol)


def normalize_asset_symbol(asset_symbol: str) -> str:
    """Normalize asset input while preserving pair notation."""
    return asset_symbol.strip().upper().replace(" ", "")


def get_ticker() -> str:
    """Backward-compatible alias for asset symbol input."""
    return get_asset_symbol()


def normalize_ticker_symbol(ticker: str) -> str:
    """Backward-compatible alias for asset symbol normalization."""
    return normalize_asset_symbol(ticker)


def get_analysis_date(default: str | None = None, timeframe: str = "1h") -> str:
    """Prompt the user to enter an analysis timestamp."""

    def validate_date(date_str: str) -> bool:
        try:
            parse_analysis_time(date_str, timeframe=timeframe)
            return True
        except ValueError:
            return False

    prompt = _analysis_time_prompt(timeframe)
    error_message = _analysis_time_error(timeframe)

    date = questionary.text(
        prompt,
        default=default or current_analysis_time(timeframe=timeframe),
        validate=lambda x: validate_date(x.strip()) or error_message,
        style=questionary.Style(
            [
                ("text", "fg:green"),
                ("highlighted", "noinherit"),
            ]
        ),
    ).ask()

    if not date:
        console.print("\n[red]No date provided. Exiting...[/red]")
        exit(1)

    return date.strip()


def select_timeframe(default: str | None = None) -> str:
    """Select runtime timeframe for market analysis."""
    timeframe_options = [
        ("1h - Intraday hourly candles", "1h"),
        ("4h - Slower intraday / swing candles", "4h"),
        ("1d - Daily candles", "1d"),
    ]

    normalized_default = default if default in VALID_TIMEFRAMES else "1h"
    choice = questionary.select(
        "Select Your [Timeframe]:",
        choices=[questionary.Choice(display, value=value) for display, value in timeframe_options],
        default=normalized_default,
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:cyan noinherit"),
                ("highlighted", "fg:cyan noinherit"),
                ("pointer", "fg:cyan noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print("\n[red]No timeframe selected. Exiting...[/red]")
        exit(1)

    return choice


def select_analysts(defaults: Iterable[AnalystType] | None = None) -> List[AnalystType]:
    """Select analysts using an interactive checkbox."""
    default_values = set(defaults or [])
    choices = [
        questionary.Choice(display, value=value, checked=value in default_values)
        for display, value in ANALYST_ORDER
    ]

    choices = questionary.checkbox(
        "Select Your [Analysts Team]:",
        choices=choices,
        initial_choice=choices[0] if choices else None,
        instruction="\n- Press Space to select/unselect analysts\n- Press 'a' to select/unselect all\n- Press Enter when done",
        validate=lambda x: len(x) > 0 or "You must select at least one analyst.",
        style=questionary.Style(
            [
                ("checkbox-selected", "fg:green"),
                ("selected", "fg:green noinherit"),
                ("highlighted", "noinherit"),
                ("pointer", "noinherit"),
            ]
        ),
    ).ask()

    if not choices:
        console.print("\n[red]No analysts selected. Exiting...[/red]")
        exit(1)

    return choices


def select_research_depth(default: int | None = None) -> int:
    """Select research depth using an interactive selection."""
    depth_options = [
        ("Shallow - Quick research, few debate and strategy discussion rounds", 1),
        ("Medium - Middle ground, moderate debate rounds and strategy discussion", 3),
        ("Deep - Comprehensive research, in depth debate and strategy discussion", 5),
    ]

    choice = questionary.select(
        "Select Your [Research Depth]:",
        choices=[
            questionary.Choice(display, value=value) for display, value in depth_options
        ],
        default=default,
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:yellow noinherit"),
                ("highlighted", "fg:yellow noinherit"),
                ("pointer", "fg:yellow noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print("\n[red]No research depth selected. Exiting...[/red]")
        exit(1)

    return choice


def _fetch_openrouter_models() -> List[Tuple[str, str]]:
    """Fetch available models from the OpenRouter API."""
    import requests

    try:
        resp = requests.get("https://openrouter.ai/api/v1/models", timeout=10)
        resp.raise_for_status()
        models = resp.json().get("data", [])
        return [(m.get("name") or m["id"], m["id"]) for m in models]
    except Exception as e:
        console.print(f"\n[yellow]Could not fetch OpenRouter models: {e}[/yellow]")
        return []


def select_openrouter_model(default: str | None = None) -> str:
    """Select an OpenRouter model from the newest available, or enter a custom ID."""
    models = _fetch_openrouter_models()

    choices = [questionary.Choice(name, value=mid) for name, mid in models[:5]]
    if default and default not in {mid for _, mid in models[:5]}:
        choices.insert(0, questionary.Choice(f"Saved model ({default})", value=default))
    choices.append(questionary.Choice("Custom model ID", value="custom"))

    choice = questionary.select(
        "Select OpenRouter Model (latest available):",
        choices=choices,
        default=default if default != "custom" else None,
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style([
            ("selected", "fg:magenta noinherit"),
            ("highlighted", "fg:magenta noinherit"),
            ("pointer", "fg:magenta noinherit"),
        ]),
    ).ask()

    if choice is None or choice == "custom":
        return questionary.text(
            "Enter OpenRouter model ID (e.g. google/gemma-4-26b-a4b-it):",
            default="" if default == "custom" else (default or ""),
            validate=lambda x: len(x.strip()) > 0 or "Please enter a model ID.",
        ).ask().strip()

    return choice


def _prompt_custom_model_id(default: str | None = None) -> str:
    """Prompt user to type a custom model ID."""
    return questionary.text(
        "Enter model ID:",
        default=default or "",
        validate=lambda x: len(x.strip()) > 0 or "Please enter a model ID.",
    ).ask().strip()


def _select_model(provider: str, mode: str, default: str | None = None) -> str:
    """Select a model for the given provider and mode (quick/deep)."""
    if provider.lower() == "openrouter":
        return select_openrouter_model(default)

    if provider.lower() == "azure":
        return questionary.text(
            f"Enter Azure deployment name ({mode}-thinking):",
            default=default or "",
            validate=lambda x: len(x.strip()) > 0 or "Please enter a deployment name.",
        ).ask().strip()

    options = get_model_options(provider, mode)
    known_values = {value for _, value in options}
    choices = [
        questionary.Choice(display, value=value)
        for display, value in options
    ]
    if default and default not in known_values:
        choices.insert(0, questionary.Choice(f"Saved model ({default})", value=default))

    choice = questionary.select(
        f"Select Your [{mode.title()}-Thinking LLM Engine]:",
        choices=choices,
        default=default if default != "custom" else None,
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print(f"\n[red]No {mode} thinking llm engine selected. Exiting...[/red]")
        exit(1)

    if choice == "custom":
        return _prompt_custom_model_id(default)

    return choice


def select_shallow_thinking_agent(provider, default: str | None = None) -> str:
    """Select shallow thinking llm engine using an interactive selection."""
    return _select_model(provider, "quick", default)


def select_deep_thinking_agent(provider, default: str | None = None) -> str:
    """Select deep thinking llm engine using an interactive selection."""
    return _select_model(provider, "deep", default)


def select_llm_provider(default_provider: str | None = None) -> tuple[str, str | None]:
    """Select the LLM provider and its API endpoint."""
    providers = [
        ("OpenAI", "openai", "https://api.openai.com/v1"),
        ("Codex Exec (no API key)", "codex_exec", None),
        ("Google", "google", None),
        ("Anthropic", "anthropic", "https://api.anthropic.com/"),
        ("xAI", "xai", "https://api.x.ai/v1"),
        ("DeepSeek", "deepseek", "https://api.deepseek.com"),
        ("Qwen", "qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        ("GLM", "glm", "https://open.bigmodel.cn/api/paas/v4/"),
        ("OpenRouter", "openrouter", "https://openrouter.ai/api/v1"),
        ("Azure OpenAI", "azure", None),
        ("Ollama", "ollama", "http://localhost:11434/v1"),
    ]

    choice = questionary.select(
        "Select your LLM Provider:",
        choices=[
            questionary.Choice(display, value=(provider_key, url))
            for display, provider_key, url in providers
        ],
        default=next(
            ((provider_key, url) for _, provider_key, url in providers if provider_key == default_provider),
            None,
        ),
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print("\n[red]No LLM provider selected. Exiting...[/red]")
        exit(1)

    provider, url = choice
    return provider, url


def ask_openai_reasoning_effort(default: str | None = None) -> str:
    """Ask for OpenAI reasoning effort level."""
    choices = [
        questionary.Choice("Medium (Default)", "medium"),
        questionary.Choice("High (More thorough)", "high"),
        questionary.Choice("Low (Faster)", "low"),
    ]
    return questionary.select(
        "Select Reasoning Effort:",
        choices=choices,
        default=default or "medium",
        style=questionary.Style([
            ("selected", "fg:cyan noinherit"),
            ("highlighted", "fg:cyan noinherit"),
            ("pointer", "fg:cyan noinherit"),
        ]),
    ).ask()


def ask_anthropic_effort(default: str | None = None) -> str | None:
    """Ask for Anthropic effort level."""
    return questionary.select(
        "Select Effort Level:",
        choices=[
            questionary.Choice("High (recommended)", "high"),
            questionary.Choice("Medium (balanced)", "medium"),
            questionary.Choice("Low (faster, cheaper)", "low"),
        ],
        default=default or "high",
        style=questionary.Style([
            ("selected", "fg:cyan noinherit"),
            ("highlighted", "fg:cyan noinherit"),
            ("pointer", "fg:cyan noinherit"),
        ]),
    ).ask()


def ask_gemini_thinking_config(default: str | None = None) -> str | None:
    """Ask for Gemini thinking configuration."""
    return questionary.select(
        "Select Thinking Mode:",
        choices=[
            questionary.Choice("Enable Thinking (recommended)", "high"),
            questionary.Choice("Minimal/Disable Thinking", "minimal"),
        ],
        default=default or "high",
        style=questionary.Style([
            ("selected", "fg:green noinherit"),
            ("highlighted", "fg:green noinherit"),
            ("pointer", "fg:green noinherit"),
        ]),
    ).ask()


def ask_output_language(default: str | None = None) -> str:
    """Ask for report output language."""
    default_choice = default or "English"
    choice_values = {
        "English",
        "Chinese",
        "Japanese",
        "Korean",
        "Hindi",
        "Spanish",
        "Portuguese",
        "French",
        "German",
        "Arabic",
        "Russian",
    }
    select_default = default_choice if default_choice in choice_values else "custom"

    choice = questionary.select(
        "Select Output Language:",
        choices=[
            questionary.Choice("English (default)", "English"),
            questionary.Choice("Chinese (中文)", "Chinese"),
            questionary.Choice("Japanese (日本語)", "Japanese"),
            questionary.Choice("Korean (한국어)", "Korean"),
            questionary.Choice("Hindi (हिन्दी)", "Hindi"),
            questionary.Choice("Spanish (Español)", "Spanish"),
            questionary.Choice("Portuguese (Português)", "Portuguese"),
            questionary.Choice("French (Français)", "French"),
            questionary.Choice("German (Deutsch)", "German"),
            questionary.Choice("Arabic (العربية)", "Arabic"),
            questionary.Choice("Russian (Русский)", "Russian"),
            questionary.Choice("Custom language", "custom"),
        ],
        default=select_default,
        style=questionary.Style([
            ("selected", "fg:yellow noinherit"),
            ("highlighted", "fg:yellow noinherit"),
            ("pointer", "fg:yellow noinherit"),
        ]),
    ).ask()

    if choice == "custom":
        return questionary.text(
            "Enter language name (e.g. Turkish, Vietnamese, Thai, Indonesian):",
            default="" if default in (None, "custom") else default,
            validate=lambda x: len(x.strip()) > 0 or "Please enter a language name.",
        ).ask().strip()

    return choice


def _analysis_time_prompt(timeframe: str) -> str:
    if timeframe == "1d":
        return "Enter the analysis date (`today` or YYYY-MM-DD):"
    return "Enter the analysis time (`now` or YYYY-MM-DD HH:MM):"


def _analysis_time_error(timeframe: str) -> str:
    if timeframe == "1d":
        return "Please enter 'today' or a valid date like YYYY-MM-DD."
    return "Please enter 'now' or a valid timestamp like YYYY-MM-DD HH:MM."
