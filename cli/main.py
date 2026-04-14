import datetime
import json
from dotenv import load_dotenv
from pathlib import Path
from typing import Any

import typer
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel

# Load environment variables
load_dotenv()
load_dotenv(".env.enterprise", override=False)

from cli.display import create_layout, update_display
from cli.models import get_analyst_label
from cli.reporting import (
    display_complete_report,
    save_report_to_disk,
)
from cli.profile import (
    DEFAULT_PROFILE_PATH,
    build_selections_from_profile,
    load_profile,
    normalize_profile,
    profile_summary,
    resolve_analysis_date,
    resolve_profile_key,
    resolve_profile_path,
    save_profile,
)
from cli.utils import (
    ask_anthropic_effort,
    ask_gemini_thinking_config,
    ask_openai_reasoning_effort,
    ask_output_language,
    get_analysis_date as prompt_analysis_date,
    get_asset_symbol as prompt_asset_symbol,
    select_analysts,
    select_deep_thinking_agent,
    select_llm_provider,
    select_research_depth,
    select_shallow_thinking_agent,
    select_timeframe,
)
from cli.announcements import fetch_announcements, display_announcements
from cli.stats_handler import StatsCallbackHandler
from tradingagents.services import run_analysis as run_analysis_service

console = Console()
TEXT_FILE_ENCODING = "utf-8"
TEXT_FILE_ERRORS = "replace"

app = typer.Typer(
    name="TradingAgents",
    help="TradingAgents CLI: Multi-Agents LLM Crypto Trading Framework",
    add_completion=True,  # Enable shell completion
)

def get_user_selections(defaults: dict[str, Any] | None = None):
    """Get all user selections before starting the analysis display."""
    defaults = normalize_profile(defaults)

    # Display ASCII art welcome message
    with open(
        Path(__file__).parent / "static" / "welcome.txt",
        "r",
        encoding=TEXT_FILE_ENCODING,
        errors=TEXT_FILE_ERRORS,
    ) as f:
        welcome_ascii = f.read()

    # Create welcome box content
    welcome_content = f"{welcome_ascii}\n"
    welcome_content += "[bold green]TradingAgents: Multi-Agents LLM Crypto Trading Framework - CLI[/bold green]\n\n"
    welcome_content += "[bold]Workflow Steps:[/bold]\n"
    welcome_content += "I. Analyst Team → II. Research Team → III. Decision Team → IV. Risk Management → V. Execution Team\n\n"
    welcome_content += (
        "[dim]Built by [Tauric Research](https://github.com/TauricResearch)[/dim]"
    )

    # Create and center the welcome box
    welcome_box = Panel(
        welcome_content,
        border_style="green",
        padding=(1, 2),
        title="Welcome to TradingAgents",
        subtitle="Multi-Agents LLM Crypto Trading Framework",
    )
    console.print(Align.center(welcome_box))
    console.print()
    console.print()  # Add vertical space before announcements

    # Fetch and display announcements (silent on failure)
    announcements = fetch_announcements()
    display_announcements(console, announcements)

    # Create a boxed questionnaire for each step
    def create_question_box(title, prompt, default=None):
        box_content = f"[bold]{title}[/bold]\n"
        box_content += f"[dim]{prompt}[/dim]"
        if default:
            box_content += f"\n[dim]Default: {default}[/dim]"
        return Panel(box_content, border_style="blue", padding=(1, 2))

    # Step 1: Asset symbol or pair
    console.print(
        create_question_box(
            "Step 1: Asset Symbol or Pair",
            "Enter the exact crypto asset symbol or pair to analyze (examples: BTC-PERP, ETH-PERP, HYPE-PERP, SOL/USDT)",
            defaults["asset_symbol"],
        )
    )
    selected_asset_symbol = prompt_asset_symbol(default=defaults["asset_symbol"])

    # Step 2: Timeframe
    default_timeframe = defaults["timeframe"]
    console.print(
        create_question_box(
            "Step 2: Timeframe",
            "Select the candle timeframe for market data and indicator windows",
            default_timeframe,
        )
    )
    selected_timeframe = select_timeframe(default=default_timeframe)

    # Step 3: Analysis time
    default_date = defaults["analysis_date"]
    console.print(
        create_question_box(
            "Step 3: Analysis Time",
            "Enter the analysis date/time aligned to the selected timeframe",
            default_date,
        )
    )
    analysis_date = prompt_analysis_date(default=default_date, timeframe=selected_timeframe)

    # Step 4: Output language
    console.print(
        create_question_box(
            "Step 4: Output Language",
            "Select the language for analyst reports and final decision",
            defaults["output_language"],
        )
    )
    output_language = ask_output_language(default=defaults["output_language"])

    # Step 5: Select analysts
    console.print(
        create_question_box(
            "Step 5: Analysts Team",
            "Select your LLM analyst agents for the analysis",
            ", ".join(defaults["analysts"]),
        )
    )
    selected_analysts = select_analysts(defaults=build_selections_from_profile(defaults)["analysts"])
    console.print(
        f"[green]Selected analysts:[/green] "
        f"{', '.join(get_analyst_label(analyst) for analyst in selected_analysts)}"
    )

    # Step 6: Research depth
    console.print(
        create_question_box(
            "Step 6: Research Depth", "Select your research depth level", defaults["research_depth"]
        )
    )
    selected_research_depth = select_research_depth(default=defaults["research_depth"])

    # Step 7: LLM Provider
    console.print(
        create_question_box(
            "Step 7: LLM Provider", "Select your LLM provider", defaults["llm_provider"]
        )
    )
    selected_llm_provider, backend_url = select_llm_provider(default_provider=defaults["llm_provider"])

    # Step 8: Thinking agents
    console.print(
        create_question_box(
            "Step 8: Thinking Agents", "Select your thinking agents for analysis"
        )
    )
    selected_shallow_thinker = select_shallow_thinking_agent(
        selected_llm_provider,
        default=defaults["shallow_thinker"],
    )
    selected_deep_thinker = select_deep_thinking_agent(
        selected_llm_provider,
        default=defaults["deep_thinker"],
    )

    # Step 9: Provider-specific thinking configuration
    thinking_level = None
    reasoning_effort = None
    anthropic_effort = None

    provider_lower = selected_llm_provider.lower()
    if provider_lower == "google":
        console.print(
            create_question_box(
                "Step 9: Thinking Mode",
                "Configure Gemini thinking mode",
                defaults.get("google_thinking_level") or "high",
            )
        )
        thinking_level = ask_gemini_thinking_config(default=defaults.get("google_thinking_level"))
    elif provider_lower == "openai":
        console.print(
            create_question_box(
                "Step 9: Reasoning Effort",
                "Configure OpenAI reasoning effort level",
                defaults.get("openai_reasoning_effort") or "medium",
            )
        )
        reasoning_effort = ask_openai_reasoning_effort(default=defaults.get("openai_reasoning_effort"))
    elif provider_lower == "anthropic":
        console.print(
            create_question_box(
                "Step 9: Effort Level",
                "Configure Claude effort level",
                defaults.get("anthropic_effort") or "high",
            )
        )
        anthropic_effort = ask_anthropic_effort(default=defaults.get("anthropic_effort"))

    return {
        "asset_symbol": selected_asset_symbol,
        "timeframe": selected_timeframe,
        "analysis_date": resolve_analysis_date(analysis_date, timeframe=selected_timeframe),
        "analysis_date_value": analysis_date,
        "analysts": selected_analysts,
        "research_depth": selected_research_depth,
        "llm_provider": selected_llm_provider.lower(),
        "backend_url": backend_url,
        "shallow_thinker": selected_shallow_thinker,
        "deep_thinker": selected_deep_thinker,
        "google_thinking_level": thinking_level,
        "openai_reasoning_effort": reasoning_effort,
        "anthropic_effort": anthropic_effort,
        "output_language": output_language,
    }

def run_analysis(
    profile_path: str | Path | None = None,
    use_saved_profile: bool = True,
):
    resolved_profile_path = resolve_profile_path(profile_path)
    try:
        raw_profile = load_profile(resolved_profile_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        console.print(f"[red]Failed to load profile JSON:[/red] {resolved_profile_path}")
        console.print(f"[dim]{exc}[/dim]\n")
        raw_profile = None

    if raw_profile and use_saved_profile:
        selections = build_selections_from_profile(raw_profile)
        console.print(
            f"[cyan]Loaded settings for profile[/cyan] {resolve_profile_key(resolved_profile_path)}"
        )
        console.print(f"[dim]{profile_summary(selections)}[/dim]\n")
    else:
        selections = get_user_selections(raw_profile)
        saved_profile_path = save_profile(
            selections,
            resolved_profile_path,
            analysis_date_value=selections.get("analysis_date_value", "now"),
            existing_profile=raw_profile,
        )
        console.print(
            f"\n[green]Saved default settings to SQLite:[/green] {saved_profile_path}"
        )
        console.print(
            f"[dim]profile_key={resolve_profile_key(resolved_profile_path)}[/dim]\n"
        )

    _run_single_analysis(selections)


def _run_single_analysis(
    selections: dict[str, Any],
    prompt_after_analysis: bool = True,
):
    selections = dict(selections)

    # Create stats callback handler for tracking LLM/tool calls
    stats_handler = StatsCallbackHandler()

    # Now start the display layout
    layout = create_layout()
    final_state = None
    results_dir = None

    with Live(layout, refresh_per_second=4):
        def render_update(message_buffer, current_stats_handler, spinner_text):
            update_display(
                layout,
                message_buffer,
                spinner_text,
                stats_handler=current_stats_handler,
            )

        result = run_analysis_service(
            selections,
            stats_handler=stats_handler,
            on_update=render_update,
        )
        final_state = result.final_state
        results_dir = result.results_dir

    if prompt_after_analysis:
        # Post-analysis prompts (outside Live context for clean interaction)
        console.print("\n[bold cyan]Analysis Complete![/bold cyan]\n")

        # Prompt to save report
        save_choice = typer.prompt("Save report?", default="Y").strip().upper()
        if save_choice in ("Y", "YES", ""):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_path = Path.cwd() / "reports" / f"{selections['asset_symbol']}_{timestamp}"
            save_path_str = typer.prompt(
                "Save path (press Enter for default)",
                default=str(default_path)
            ).strip()
            save_path = Path(save_path_str)
            try:
                report_file = save_report_to_disk(
                    final_state,
                    selections["asset_symbol"],
                    save_path,
                    encoding=TEXT_FILE_ENCODING,
                    errors=TEXT_FILE_ERRORS,
                )
                console.print(f"\n[green]✓ Report saved to:[/green] {save_path.resolve()}")
                console.print(f"  [dim]Complete report:[/dim] {report_file.name}")
            except Exception as e:
                console.print(f"[red]Error saving report: {e}[/red]")

        # Prompt to display full report
        display_choice = typer.prompt("\nDisplay full report on screen?", default="Y").strip().upper()
        if display_choice in ("Y", "YES", ""):
            display_complete_report(console, final_state)

    return final_state, results_dir


@app.command()
def analyze(
    profile: Path = typer.Option(
        DEFAULT_PROFILE_PATH,
        "--profile",
        help="Path to the JSON file used for saved run defaults.",
    ),
    edit_profile: bool = typer.Option(
        False,
        "--edit-profile",
        help="Edit prompts and overwrite the saved JSON profile before running.",
    ),
):
    run_analysis(
        profile_path=profile,
        use_saved_profile=not edit_profile,
    )


if __name__ == "__main__":
    app()
