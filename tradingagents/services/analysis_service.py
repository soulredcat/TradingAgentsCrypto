from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cli.message_buffer import MessageBuffer
from cli.models import AnalystType, normalize_analyst_type
from cli.reporting import attach_analysis_persistence
from cli.runtime import (
    ANALYST_AGENT_NAMES,
    ANALYST_ORDER,
    DECISION_AGENT_NAMES,
    POST_DECISION_AGENT_NAMES,
    POST_PORTFOLIO_RISK_AGENT_NAMES,
    POST_RESEARCH_AGENT_NAMES,
    POST_TRADE_RISK_AGENT_NAMES,
    RESEARCH_AGENT_NAMES,
    analysts_phase_completed,
    classify_message_type,
    decision_phase_completed,
    portfolio_risk_phase_completed,
    research_phase_completed,
    set_agent_group_pending,
    trade_risk_phase_completed,
    update_analyst_statuses,
    update_research_debate_statuses,
)
from cli.stats_handler import StatsCallbackHandler
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.storage import SQLiteRepository
from cli.profile import format_analysis_date_for_path


UpdateCallback = Callable[[MessageBuffer, StatsCallbackHandler | None, str | None], None]


@dataclass
class AnalysisRunContext:
    selections: dict[str, Any]
    config: dict[str, Any]
    repository: SQLiteRepository
    run_id: int
    results_dir: Path
    selected_analyst_keys: list[str]


@dataclass
class AnalysisExecutionResult:
    final_state: dict[str, Any]
    results_dir: Path
    run_id: int
    message_buffer: MessageBuffer
    stats_handler: StatsCallbackHandler


def prepare_analysis_context(
    selections: dict[str, Any],
    repository: SQLiteRepository | None = None,
    run_id: int | None = None,
) -> AnalysisRunContext:
    normalized_selections = dict(selections)
    ordered_analysts: list[AnalystType] = []
    selected_analyst_values = {
        normalize_analyst_type(analyst).value
        for analyst in normalized_selections["analysts"]
    }
    for analyst_key in ANALYST_ORDER:
        analyst_enum = AnalystType(analyst_key)
        if analyst_enum.value in selected_analyst_values:
            ordered_analysts.append(analyst_enum)
    normalized_selections["analysts"] = ordered_analysts

    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = normalized_selections["research_depth"]
    config["max_risk_discuss_rounds"] = normalized_selections["research_depth"]
    config["quick_think_llm"] = normalized_selections["shallow_thinker"]
    config["deep_think_llm"] = normalized_selections["deep_thinker"]
    config["timeframe"] = normalized_selections["timeframe"]
    config["backend_url"] = normalized_selections["backend_url"]
    config["llm_provider"] = normalized_selections["llm_provider"].lower()
    config["storage_retention_days"] = normalized_selections["storage_retention_days"]
    config["storage_max_runs_per_asset_timeframe"] = normalized_selections[
        "storage_max_runs_per_asset_timeframe"
    ]
    config["storage_max_reflection_entries_per_memory"] = normalized_selections[
        "storage_max_reflection_entries_per_memory"
    ]
    config["google_thinking_level"] = normalized_selections.get("google_thinking_level")
    config["openai_reasoning_effort"] = normalized_selections.get(
        "openai_reasoning_effort"
    )
    config["anthropic_effort"] = normalized_selections.get("anthropic_effort")
    config["output_language"] = normalized_selections.get("output_language", "English")

    selected_set = {analyst.value for analyst in normalized_selections["analysts"]}
    selected_analyst_keys = [key for key in ANALYST_ORDER if key in selected_set]

    analysis_path_segment = format_analysis_date_for_path(
        normalized_selections["analysis_date"],
        timeframe=normalized_selections["timeframe"],
    )
    results_dir = (
        Path(config["results_dir"])
        / normalized_selections["asset_symbol"]
        / analysis_path_segment
    )
    results_dir.mkdir(parents=True, exist_ok=True)

    repository = repository or SQLiteRepository(config=config)
    if run_id is None:
        run_id = repository.create_analysis_run(
            asset_symbol=normalized_selections["asset_symbol"],
            timeframe=normalized_selections["timeframe"],
            analysis_time=normalized_selections["analysis_date"],
            results_dir=results_dir,
            config=config,
        )
    config["analysis_run_id"] = run_id

    return AnalysisRunContext(
        selections=normalized_selections,
        config=config,
        repository=repository,
        run_id=run_id,
        results_dir=results_dir,
        selected_analyst_keys=selected_analyst_keys,
    )


def execute_analysis_context(
    context: AnalysisRunContext,
    *,
    stats_handler: StatsCallbackHandler | None = None,
    message_buffer: MessageBuffer | None = None,
    on_update: UpdateCallback | None = None,
) -> AnalysisExecutionResult:
    stats_handler = stats_handler or StatsCallbackHandler()

    graph = TradingAgentsGraph(
        context.selected_analyst_keys,
        config=context.config,
        debug=True,
        callbacks=[stats_handler],
    )

    message_buffer = message_buffer or MessageBuffer()
    message_buffer.init_for_analysis(context.selected_analyst_keys)
    attach_analysis_persistence(
        message_buffer,
        repository=context.repository,
        run_id=context.run_id,
    )

    spinner_text = (
        f"Analyzing {context.selections['asset_symbol']} on "
        f"{context.selections['timeframe']} at {context.selections['analysis_date']}..."
    )

    _sync_progress(context, message_buffer, stats_handler)
    _emit_update(on_update, message_buffer, stats_handler, None)

    final_state: dict[str, Any] | None = None
    try:
        message_buffer.add_message(
            "System", f"Selected asset: {context.selections['asset_symbol']}"
        )
        message_buffer.add_message(
            "System", f"Selected timeframe: {context.selections['timeframe']}"
        )
        message_buffer.add_message(
            "System", f"Analysis time: {context.selections['analysis_date']}"
        )
        message_buffer.add_message(
            "System",
            "Selected analysts: "
            + ", ".join(
                ANALYST_AGENT_NAMES[analyst.value]
                for analyst in context.selections["analysts"]
            ),
        )
        first_analyst = ANALYST_AGENT_NAMES[context.selections["analysts"][0].value]
        message_buffer.update_agent_status(first_analyst, "in_progress")
        _sync_progress(context, message_buffer, stats_handler)
        _emit_update(on_update, message_buffer, stats_handler, spinner_text)

        init_agent_state = graph.propagator.create_initial_state(
            context.selections["asset_symbol"],
            context.selections["analysis_date"],
        )
        args = graph.propagator.get_graph_args(callbacks=[stats_handler])

        trace: list[dict[str, Any]] = []
        for chunk in graph.graph.stream(init_agent_state, **args):
            _apply_chunk_to_message_buffer(
                message_buffer=message_buffer,
                chunk=chunk,
                research_depth=context.selections["research_depth"],
            )
            _sync_progress(context, message_buffer, stats_handler)
            _emit_update(on_update, message_buffer, stats_handler, spinner_text)
            trace.append(chunk)

        final_state = trace[-1]
        graph.process_signal(final_state["trader_investment_plan"])
        context.repository.save_full_state_log(
            trade_date=final_state["trade_date"],
            payload=_build_persisted_final_state(final_state),
            run_id=context.run_id,
            asset_symbol=final_state["asset_symbol"],
        )

        message_buffer.add_message(
            "System",
            f"Completed analysis for {context.selections['analysis_date']}",
        )

        for section in message_buffer.report_sections.keys():
            if section in final_state:
                message_buffer.update_report_section(section, final_state[section])

        if message_buffer.final_report:
            context.repository.save_complete_report(
                run_id=context.run_id,
                asset_symbol=context.selections["asset_symbol"],
                markdown=message_buffer.final_report,
            )

        context.repository.update_analysis_run_status(context.run_id, "completed")
        _sync_progress(context, message_buffer, stats_handler)
        _emit_update(on_update, message_buffer, stats_handler, None)
    except Exception as exc:
        message_buffer.add_message("System", f"Run failed: {exc}")
        context.repository.update_analysis_run_status(context.run_id, "failed")
        _sync_progress(context, message_buffer, stats_handler)
        _emit_update(on_update, message_buffer, stats_handler, None)
        raise

    return AnalysisExecutionResult(
        final_state=final_state or {},
        results_dir=context.results_dir,
        run_id=context.run_id,
        message_buffer=message_buffer,
        stats_handler=stats_handler,
    )


def run_analysis(
    selections: dict[str, Any],
    *,
    repository: SQLiteRepository | None = None,
    run_id: int | None = None,
    stats_handler: StatsCallbackHandler | None = None,
    message_buffer: MessageBuffer | None = None,
    on_update: UpdateCallback | None = None,
) -> AnalysisExecutionResult:
    context = prepare_analysis_context(
        selections,
        repository=repository,
        run_id=run_id,
    )
    return execute_analysis_context(
        context,
        stats_handler=stats_handler,
        message_buffer=message_buffer,
        on_update=on_update,
    )


def _emit_update(
    on_update: UpdateCallback | None,
    message_buffer: MessageBuffer,
    stats_handler: StatsCallbackHandler | None,
    spinner_text: str | None,
) -> None:
    if on_update is not None:
        on_update(message_buffer, stats_handler, spinner_text)


def _sync_progress(
    context: AnalysisRunContext,
    message_buffer: MessageBuffer,
    stats_handler: StatsCallbackHandler | None,
) -> None:
    context.repository.upsert_analysis_progress(
        run_id=context.run_id,
        selected_analysts=list(message_buffer.selected_analysts),
        agent_status=dict(message_buffer.agent_status),
        report_sections={
            key: value for key, value in message_buffer.report_sections.items() if value
        },
        current_agent=message_buffer.current_agent,
        current_report=message_buffer.current_report,
        stats=stats_handler.get_stats() if stats_handler else {},
    )


def _apply_chunk_to_message_buffer(
    *,
    message_buffer: MessageBuffer,
    chunk: dict[str, Any],
    research_depth: int,
) -> None:
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

    update_analyst_statuses(message_buffer, chunk)
    analysts_done = analysts_phase_completed(message_buffer)
    if not analysts_done:
        set_agent_group_pending(message_buffer, RESEARCH_AGENT_NAMES)
        set_agent_group_pending(message_buffer, POST_RESEARCH_AGENT_NAMES)

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
            research_depth,
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
        message_buffer.update_report_section("decision_plan", chunk["decision_plan"])
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
            message_buffer.update_agent_status("Portfolio Risk Analyst", "completed")
    elif trade_risk_done:
        if message_buffer.agent_status.get("Portfolio Risk Analyst") == "pending":
            message_buffer.update_agent_status("Portfolio Risk Analyst", "in_progress")
    else:
        set_agent_group_pending(message_buffer, POST_TRADE_RISK_AGENT_NAMES)

    portfolio_risk_done = portfolio_risk_phase_completed(message_buffer)
    if portfolio_risk_done and chunk.get("trader_investment_plan"):
        message_buffer.update_report_section(
            "trader_investment_plan",
            chunk["trader_investment_plan"],
        )
        if message_buffer.agent_status.get("Execution Team") != "completed":
            message_buffer.update_agent_status("Execution Team", "completed")
    elif portfolio_risk_done:
        if message_buffer.agent_status.get("Execution Team") == "pending":
            message_buffer.update_agent_status("Execution Team", "in_progress")
    else:
        set_agent_group_pending(message_buffer, POST_PORTFOLIO_RISK_AGENT_NAMES)


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
            "current_response": final_state["investment_debate_state"][
                "current_response"
            ],
            "judge_decision": final_state["investment_debate_state"][
                "judge_decision"
            ],
        },
        "trader_investment_plan": final_state["trader_investment_plan"],
        "trade_risk_assessment": final_state["trade_risk_assessment"],
        "portfolio_risk_assessment": final_state["portfolio_risk_assessment"],
        "investment_plan": final_state["investment_plan"],
    }
