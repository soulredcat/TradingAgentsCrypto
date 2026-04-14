import datetime
from pathlib import Path

from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule

from tradingagents.storage import SQLiteRepository


def attach_analysis_persistence(
    message_buffer,
    repository: SQLiteRepository,
    run_id: int,
):
    def save_message_decorator(obj, func_name):
        original_func = getattr(obj, func_name)

        def wrapper(*args, **kwargs):
            original_func(*args, **kwargs)
            timestamp, message_type, content = obj.messages[-1]
            repository.append_message(run_id, timestamp, message_type, str(content))

        return wrapper

    def save_tool_call_decorator(obj, func_name):
        original_func = getattr(obj, func_name)

        def wrapper(*args, **kwargs):
            original_func(*args, **kwargs)
            timestamp, tool_name, tool_args = obj.tool_calls[-1]
            repository.append_tool_call(run_id, timestamp, tool_name, tool_args)

        return wrapper

    def save_report_section_decorator(obj, func_name):
        original_func = getattr(obj, func_name)

        def wrapper(section_name, content):
            original_func(section_name, content)
            if section_name in obj.report_sections and obj.report_sections[section_name] is not None:
                section_content = obj.report_sections[section_name]
                if section_content:
                    text = (
                        "\n".join(str(item) for item in section_content)
                        if isinstance(section_content, list)
                        else str(section_content)
                    )
                    repository.upsert_report_section(run_id, section_name, text)

        return wrapper

    message_buffer.add_message = save_message_decorator(message_buffer, "add_message")
    message_buffer.add_tool_call = save_tool_call_decorator(
        message_buffer, "add_tool_call"
    )
    message_buffer.update_report_section = save_report_section_decorator(
        message_buffer, "update_report_section"
    )
    return message_buffer


def save_report_to_disk(
    final_state,
    asset_symbol: str,
    save_path: Path,
    encoding: str = "utf-8",
    errors: str = "replace",
):
    save_path.mkdir(parents=True, exist_ok=True)
    sections = []

    analysts_dir = save_path / "1_analysts"
    analyst_parts = []
    if final_state.get("market_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "market.md").write_text(
            final_state["market_report"], encoding=encoding, errors=errors
        )
        analyst_parts.append(("Market Structure Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "volume_flow.md").write_text(
            final_state["sentiment_report"], encoding=encoding, errors=errors
        )
        analyst_parts.append(("Volume Flow Analyst", final_state["sentiment_report"]))
    if final_state.get("funding_oi_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "funding_oi.md").write_text(
            final_state["funding_oi_report"], encoding=encoding, errors=errors
        )
        analyst_parts.append(("Funding & OI Analyst", final_state["funding_oi_report"]))
    if final_state.get("news_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "news.md").write_text(
            final_state["news_report"], encoding=encoding, errors=errors
        )
        analyst_parts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("tokenomics_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "tokenomics_onchain.md").write_text(
            final_state["tokenomics_report"], encoding=encoding, errors=errors
        )
        analyst_parts.append(
            ("Tokenomics & On-Chain Analyst", final_state["tokenomics_report"])
        )
    if analyst_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. Analyst Team Reports\n\n{content}")

    if final_state.get("investment_debate_state"):
        research_dir = save_path / "2_research"
        debate = final_state["investment_debate_state"]
        research_parts = []
        if debate.get("bull_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bull.md").write_text(
                debate["bull_history"], encoding=encoding, errors=errors
            )
            research_parts.append(("Bull Thesis", debate["bull_history"]))
        if debate.get("bear_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bear.md").write_text(
                debate["bear_history"], encoding=encoding, errors=errors
            )
            research_parts.append(("Bear Thesis", debate["bear_history"]))
        if debate.get("judge_decision"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "manager.md").write_text(
                debate["judge_decision"], encoding=encoding, errors=errors
            )
            research_parts.append(("Research Verdict", debate["judge_decision"]))
        if research_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in research_parts)
            sections.append(f"## II. Research Team Verdict\n\n{content}")

    if final_state.get("setup_classification"):
        decision_dir = save_path / "3_decision"
        decision_dir.mkdir(exist_ok=True)
        (decision_dir / "setup_classifier.md").write_text(
            final_state["setup_classification"], encoding=encoding, errors=errors
        )
        decision_parts = [
            (
                "Setup Classifier",
                final_state["setup_classification"],
            )
        ]
        if final_state.get("decision_plan"):
            (decision_dir / "decision_engine.md").write_text(
                final_state["decision_plan"], encoding=encoding, errors=errors
            )
            decision_parts.append(("Decision Engine", final_state["decision_plan"]))
        content = "\n\n".join(f"### {name}\n{text}" for name, text in decision_parts)
        sections.append(f"## III. Decision Team Outputs\n\n{content}")
    elif final_state.get("decision_plan"):
        decision_dir = save_path / "3_decision"
        decision_dir.mkdir(exist_ok=True)
        (decision_dir / "decision_engine.md").write_text(
            final_state["decision_plan"], encoding=encoding, errors=errors
        )
        sections.append(
            "## III. Decision Team Outputs\n\n### Decision Engine\n"
            f"{final_state['decision_plan']}"
        )

    if final_state.get("trade_risk_assessment"):
        risk_dir = save_path / "4_risk"
        risk_dir.mkdir(exist_ok=True)
        (risk_dir / "trade_risk.md").write_text(
            final_state["trade_risk_assessment"], encoding=encoding, errors=errors
        )
        sections.append(
            "## IV. Risk Management Trade Risk Assessment\n\n### Trade Risk Analyst\n"
            f"{final_state['trade_risk_assessment']}"
        )

    if final_state.get("portfolio_risk_assessment"):
        risk_dir = save_path / "4_risk"
        risk_dir.mkdir(exist_ok=True)
        (risk_dir / "portfolio_risk.md").write_text(
            final_state["portfolio_risk_assessment"], encoding=encoding, errors=errors
        )
        sections.append(
            "## V. Risk Management Portfolio Risk Assessment\n\n### Portfolio Risk Analyst\n"
            f"{final_state['portfolio_risk_assessment']}"
        )

    if final_state.get("trader_investment_plan"):
        execution_dir = save_path / "5_execution"
        execution_dir.mkdir(exist_ok=True)
        (execution_dir / "execution_team.md").write_text(
            final_state["trader_investment_plan"], encoding=encoding, errors=errors
        )
        sections.append(
            "## VI. Execution Team Plan\n\n### Execution Team\n"
            f"{final_state['trader_investment_plan']}"
        )

    header = (
        f"# Crypto Trading Analysis Report: {asset_symbol}\n\nGenerated: "
        f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    report_file = save_path / "complete_report.md"
    report_file.write_text(
        header + "\n\n".join(sections), encoding=encoding, errors=errors
    )
    return report_file


def display_complete_report(console, final_state):
    console.print()
    console.print(Rule("Complete Analysis Report", style="bold green"))

    analysts = []
    if final_state.get("market_report"):
        analysts.append(("Market Structure Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analysts.append(("Volume Flow Analyst", final_state["sentiment_report"]))
    if final_state.get("funding_oi_report"):
        analysts.append(("Funding & OI Analyst", final_state["funding_oi_report"]))
    if final_state.get("news_report"):
        analysts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("tokenomics_report"):
        analysts.append(("Tokenomics & On-Chain Analyst", final_state["tokenomics_report"]))
    if analysts:
        console.print(Panel("[bold]I. Analyst Team Reports[/bold]", border_style="cyan"))
        for title, content in analysts:
            console.print(
                Panel(Markdown(content), title=title, border_style="blue", padding=(1, 2))
            )

    if final_state.get("investment_debate_state"):
        debate = final_state["investment_debate_state"]
        research = []
        if debate.get("bull_history"):
            research.append(("Bull Thesis", debate["bull_history"]))
        if debate.get("bear_history"):
            research.append(("Bear Thesis", debate["bear_history"]))
        if debate.get("judge_decision"):
            research.append(("Research Verdict", debate["judge_decision"]))
        if research:
            console.print(
                Panel("[bold]II. Research Team Verdict[/bold]", border_style="magenta")
            )
            for title, content in research:
                console.print(
                    Panel(Markdown(content), title=title, border_style="blue", padding=(1, 2))
                )

    if final_state.get("setup_classification") or final_state.get("decision_plan"):
        console.print(Panel("[bold]III. Decision Team Outputs[/bold]", border_style="cyan"))
        if final_state.get("setup_classification"):
            console.print(
                Panel(
                    Markdown(final_state["setup_classification"]),
                    title="Setup Classifier",
                    border_style="blue",
                    padding=(1, 2),
                )
            )
        if final_state.get("decision_plan"):
            console.print(
                Panel(
                    Markdown(final_state["decision_plan"]),
                    title="Decision Engine",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

    if final_state.get("trade_risk_assessment"):
        console.print(
            Panel("[bold]IV. Risk Management Trade Risk Assessment[/bold]", border_style="red")
        )
        console.print(
            Panel(
                Markdown(final_state["trade_risk_assessment"]),
                title="Trade Risk Analyst",
                border_style="blue",
                padding=(1, 2),
            )
        )

    if final_state.get("portfolio_risk_assessment"):
        console.print(
            Panel("[bold]V. Risk Management Portfolio Risk Assessment[/bold]", border_style="red")
        )
        console.print(
            Panel(
                Markdown(final_state["portfolio_risk_assessment"]),
                title="Portfolio Risk Analyst",
                border_style="blue",
                padding=(1, 2),
            )
        )

    if final_state.get("trader_investment_plan"):
        console.print(Panel("[bold]VI. Execution Team Plan[/bold]", border_style="yellow"))
        console.print(
            Panel(
                Markdown(final_state["trader_investment_plan"]),
                title="Execution Team",
                border_style="blue",
                padding=(1, 2),
            )
        )
