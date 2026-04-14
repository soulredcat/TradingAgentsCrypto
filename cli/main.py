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

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from cli.display import create_layout, update_display
from cli.message_buffer import MessageBuffer
from cli.models import AnalystType, get_analyst_label
from cli.reporting import (
    attach_analysis_persistence,
    display_complete_report,
    save_report_to_disk,
)
from cli.profile import (
    DEFAULT_PROFILE_PATH,
    build_selections_from_profile,
    format_analysis_date_for_path,
    load_profile,
    normalize_profile,
    profile_summary,
    resolve_analysis_date,
    resolve_profile_key,
    resolve_profile_path,
    save_profile,
)
from cli.runtime import (
    ANALYST_ORDER,
    ANALYST_AGENT_NAMES,
    DECISION_AGENT_NAMES,
    POST_DECISION_AGENT_NAMES,
    POST_EXECUTION_AGENT_NAMES,
    POST_PORTFOLIO_RISK_AGENT_NAMES,
    POST_RESEARCH_AGENT_NAMES,
    POST_TRADE_RISK_AGENT_NAMES,
    RESEARCH_AGENT_NAMES,
    analysts_phase_completed,
    classify_message_type,
    decision_phase_completed,
    execution_phase_completed,
    portfolio_risk_phase_completed,
    research_phase_completed,
    set_agent_group_pending,
    trade_risk_phase_completed,
    update_analyst_statuses,
    update_research_debate_statuses,
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
from tradingagents.storage import SQLiteRepository

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

    ordered_analysts = []
    selected_analyst_values = {analyst.value for analyst in selections["analysts"]}
    for analyst_key in ANALYST_ORDER:
        analyst_enum = AnalystType(analyst_key)
        if analyst_enum.value in selected_analyst_values:
            ordered_analysts.append(analyst_enum)
    selections["analysts"] = ordered_analysts

    # Create config with selected research depth
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = selections["research_depth"]
    config["max_risk_discuss_rounds"] = selections["research_depth"]
    config["quick_think_llm"] = selections["shallow_thinker"]
    config["deep_think_llm"] = selections["deep_thinker"]
    config["timeframe"] = selections["timeframe"]
    config["backend_url"] = selections["backend_url"]
    config["llm_provider"] = selections["llm_provider"].lower()
    # Provider-specific thinking configuration
    config["google_thinking_level"] = selections.get("google_thinking_level")
    config["openai_reasoning_effort"] = selections.get("openai_reasoning_effort")
    config["anthropic_effort"] = selections.get("anthropic_effort")
    config["output_language"] = selections.get("output_language", "English")

    # Create stats callback handler for tracking LLM/tool calls
    stats_handler = StatsCallbackHandler()

    # Normalize analyst selection to predefined order (selection is a 'set', order is fixed)
    selected_set = {analyst.value for analyst in selections["analysts"]}
    selected_analyst_keys = [a for a in ANALYST_ORDER if a in selected_set]

    # Create result directory
    analysis_path_segment = format_analysis_date_for_path(
        selections["analysis_date"],
        timeframe=selections["timeframe"],
    )
    results_dir = Path(config["results_dir"]) / selections["asset_symbol"] / analysis_path_segment
    results_dir.mkdir(parents=True, exist_ok=True)
    repository = SQLiteRepository(config=config)
    run_id = repository.create_analysis_run(
        asset_symbol=selections["asset_symbol"],
        timeframe=selections["timeframe"],
        analysis_time=selections["analysis_date"],
        results_dir=results_dir,
        config=config,
    )
    config["analysis_run_id"] = run_id

    # Initialize the graph with callbacks bound to LLMs
    graph = TradingAgentsGraph(
        selected_analyst_keys,
        config=config,
        debug=True,
        callbacks=[stats_handler],
    )

    message_buffer = MessageBuffer()
    message_buffer.init_for_analysis(selected_analyst_keys)

    attach_analysis_persistence(
        message_buffer,
        repository=repository,
        run_id=run_id,
    )

    # Now start the display layout
    layout = create_layout()

    try:
        with Live(layout, refresh_per_second=4):
            # Initial display
            update_display(
                layout,
                message_buffer,
                stats_handler=stats_handler,
            )

            # Add initial messages
            message_buffer.add_message("System", f"Selected asset: {selections['asset_symbol']}")
            message_buffer.add_message("System", f"Selected timeframe: {selections['timeframe']}")
            message_buffer.add_message(
                "System", f"Analysis time: {selections['analysis_date']}"
            )
            message_buffer.add_message(
                "System",
                f"Selected analysts: {', '.join(get_analyst_label(analyst) for analyst in selections['analysts'])}",
            )
            update_display(
                layout,
                message_buffer,
                stats_handler=stats_handler,
            )

            # Update agent status to in_progress for the first analyst
            first_analyst = ANALYST_AGENT_NAMES[selections["analysts"][0].value]
            message_buffer.update_agent_status(first_analyst, "in_progress")
            update_display(
                layout,
                message_buffer,
                stats_handler=stats_handler,
            )

            # Create spinner text
            spinner_text = (
                f"Analyzing {selections['asset_symbol']} on "
                f"{selections['timeframe']} at {selections['analysis_date']}..."
            )
            update_display(
                layout,
                message_buffer,
                spinner_text,
                stats_handler=stats_handler,
            )

            # Initialize state and get graph args with callbacks
            init_agent_state = graph.propagator.create_initial_state(
                selections["asset_symbol"], selections["analysis_date"]
            )
            # Pass callbacks to graph config for tool execution tracking
            # (LLM tracking is handled separately via LLM constructor)
            args = graph.propagator.get_graph_args(callbacks=[stats_handler])

            # Stream the analysis
            trace = []
            for chunk in graph.graph.stream(init_agent_state, **args):
                # Process all messages in chunk, deduplicating by message ID
                for message in chunk.get("messages", []):
                    msg_id = getattr(message, "id", None)
                    if msg_id is not None:
                        if msg_id in message_buffer._processed_message_ids:
                            continue
                        message_buffer._processed_message_ids.add(msg_id)

                    msg_type, content = classify_message_type(message)
                    if content and content.strip():
                        message_buffer.add_message(msg_type, content)

                    if hasattr(message, "tool_calls") and message.tool_calls:
                        for tool_call in message.tool_calls:
                            if isinstance(tool_call, dict):
                                message_buffer.add_tool_call(tool_call["name"], tool_call["args"])
                            else:
                                message_buffer.add_tool_call(tool_call.name, tool_call.args)

                # Update analyst statuses based on report state (runs on every chunk)
                update_analyst_statuses(message_buffer, chunk)
                analysts_done = analysts_phase_completed(message_buffer)
                if not analysts_done:
                    set_agent_group_pending(message_buffer, RESEARCH_AGENT_NAMES)
                    set_agent_group_pending(message_buffer, POST_RESEARCH_AGENT_NAMES)

                # Research Team - Handle Investment Debate State
                if analysts_done and chunk.get("investment_debate_state"):
                    debate_state = chunk["investment_debate_state"]
                    bull_hist = debate_state.get("bull_history", "").strip()
                    bear_hist = debate_state.get("bear_history", "").strip()
                    judge = debate_state.get("judge_decision", "").strip()

                    if bull_hist:
                        message_buffer.update_report_section(
                            "investment_plan", f"### Bull Thesis\n{bull_hist}"
                        )
                    if bear_hist:
                        message_buffer.update_report_section(
                            "investment_plan", f"### Bear Thesis\n{bear_hist}"
                        )
                    if judge:
                        message_buffer.update_report_section(
                            "investment_plan", f"### Research Verdict\n{judge}"
                        )

                    update_research_debate_statuses(
                        message_buffer,
                        debate_state,
                        selections["research_depth"],
                    )
                else:
                    set_agent_group_pending(message_buffer, RESEARCH_AGENT_NAMES)

                research_done = research_phase_completed(message_buffer)
                if not research_done:
                    set_agent_group_pending(message_buffer, DECISION_AGENT_NAMES)
                    set_agent_group_pending(message_buffer, POST_RESEARCH_AGENT_NAMES)

                if research_done and chunk.get("setup_classification"):
                    message_buffer.update_report_section(
                        "setup_classification", chunk["setup_classification"]
                    )
                    if message_buffer.agent_status.get("Setup Classifier") != "completed":
                        message_buffer.update_agent_status("Setup Classifier", "completed")
                elif research_done:
                    if message_buffer.agent_status.get("Setup Classifier") == "pending":
                        message_buffer.update_agent_status("Setup Classifier", "in_progress")
                else:
                    set_agent_group_pending(message_buffer, DECISION_AGENT_NAMES)

                setup_done = message_buffer.agent_status.get("Setup Classifier") == "completed"
                if research_done and setup_done and chunk.get("decision_plan"):
                    message_buffer.update_report_section(
                        "decision_plan", chunk["decision_plan"]
                    )
                    if message_buffer.agent_status.get("Decision Engine") != "completed":
                        message_buffer.update_agent_status("Decision Engine", "completed")
                elif research_done and setup_done:
                    if message_buffer.agent_status.get("Decision Engine") == "pending":
                        message_buffer.update_agent_status("Decision Engine", "in_progress")
                elif research_done:
                    if message_buffer.agent_status.get("Decision Engine") != "completed":
                        message_buffer.update_agent_status("Decision Engine", "pending")

                decision_done = decision_phase_completed(message_buffer)
                if not decision_done:
                    set_agent_group_pending(message_buffer, POST_DECISION_AGENT_NAMES)

                if decision_done and chunk.get("trade_risk_assessment"):
                    message_buffer.update_report_section(
                        "trade_risk_assessment", chunk["trade_risk_assessment"]
                    )
                    if message_buffer.agent_status.get("Trade Risk Analyst") != "completed":
                        message_buffer.update_agent_status("Trade Risk Analyst", "completed")
                elif decision_done:
                    if message_buffer.agent_status.get("Trade Risk Analyst") == "pending":
                        message_buffer.update_agent_status("Trade Risk Analyst", "in_progress")
                else:
                    set_agent_group_pending(message_buffer, POST_DECISION_AGENT_NAMES)

                trade_risk_done = trade_risk_phase_completed(message_buffer)
                if trade_risk_done and chunk.get("portfolio_risk_assessment"):
                    message_buffer.update_report_section(
                        "portfolio_risk_assessment",
                        chunk["portfolio_risk_assessment"],
                    )
                    if message_buffer.agent_status.get("Portfolio Risk Analyst") != "completed":
                        message_buffer.update_agent_status(
                            "Portfolio Risk Analyst", "completed"
                        )
                elif trade_risk_done:
                    if message_buffer.agent_status.get("Portfolio Risk Analyst") == "pending":
                        message_buffer.update_agent_status(
                            "Portfolio Risk Analyst", "in_progress"
                        )
                else:
                    set_agent_group_pending(message_buffer, POST_TRADE_RISK_AGENT_NAMES)

                portfolio_risk_done = portfolio_risk_phase_completed(message_buffer)
                if portfolio_risk_done and chunk.get("trader_investment_plan"):
                    message_buffer.update_report_section(
                        "trader_investment_plan", chunk["trader_investment_plan"]
                    )
                    if message_buffer.agent_status.get("Execution Team") != "completed":
                        message_buffer.update_agent_status("Execution Team", "completed")
                elif portfolio_risk_done:
                    if message_buffer.agent_status.get("Execution Team") == "pending":
                        message_buffer.update_agent_status("Execution Team", "in_progress")
                else:
                    set_agent_group_pending(
                        message_buffer, POST_PORTFOLIO_RISK_AGENT_NAMES
                    )

                # Update the display
                update_display(
                    layout,
                    message_buffer,
                    stats_handler=stats_handler,
                )

                trace.append(chunk)

            # Get final state and decision
            final_state = trace[-1]
            graph.process_signal(final_state["trader_investment_plan"])
            repository.save_full_state_log(
                trade_date=final_state["trade_date"],
                payload=_build_persisted_final_state(final_state),
                run_id=run_id,
                asset_symbol=final_state["asset_symbol"],
            )

            message_buffer.add_message(
                "System", f"Completed analysis for {selections['analysis_date']}"
            )

            # Update final report sections
            for section in message_buffer.report_sections.keys():
                if section in final_state:
                    message_buffer.update_report_section(section, final_state[section])

            update_display(
                layout,
                message_buffer,
                stats_handler=stats_handler,
            )
            if message_buffer.final_report:
                repository.save_complete_report(
                    run_id=run_id,
                    asset_symbol=selections["asset_symbol"],
                    markdown=message_buffer.final_report,
                )
            repository.update_analysis_run_status(run_id, "completed")
    except Exception:
        repository.update_analysis_run_status(run_id, "failed")
        raise

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


def _build_persisted_final_state(final_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_symbol": final_state["asset_symbol"],
        "trade_date": final_state["trade_date"],
        "market_report": final_state["market_report"],
        "sentiment_report": final_state["sentiment_report"],
        "funding_oi_report": final_state["funding_oi_report"],
        "news_report": final_state["news_report"],
        "tokenomics_report": final_state["tokenomics_report"],
        "setup_classification": final_state["setup_classification"],
        "decision_plan": final_state["decision_plan"],
        "investment_debate_state": {
            "bull_history": final_state["investment_debate_state"]["bull_history"],
            "bear_history": final_state["investment_debate_state"]["bear_history"],
            "history": final_state["investment_debate_state"]["history"],
            "current_response": final_state["investment_debate_state"]["current_response"],
            "judge_decision": final_state["investment_debate_state"]["judge_decision"],
        },
        "trader_investment_plan": final_state["trader_investment_plan"],
        "trade_risk_assessment": final_state["trade_risk_assessment"],
        "portfolio_risk_assessment": final_state["portfolio_risk_assessment"],
        "investment_plan": final_state["investment_plan"],
    }


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
