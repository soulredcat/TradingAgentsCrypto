import datetime
from functools import wraps
from pathlib import Path

from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule


def attach_analysis_persistence(
    message_buffer,
    log_file: Path,
    report_dir: Path,
    encoding: str = "utf-8",
    errors: str = "replace",
):
    def save_message_decorator(obj, func_name):
        func = getattr(obj, func_name)

        @wraps(func)
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)
            timestamp, message_type, content = obj.messages[-1]
            safe_content = str(content).replace("\n", " ")
            with open(log_file, "a", encoding=encoding, errors=errors) as file_obj:
                file_obj.write(f"{timestamp} [{message_type}] {safe_content}\n")

        return wrapper

    def save_tool_call_decorator(obj, func_name):
        func = getattr(obj, func_name)

        @wraps(func)
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)
            timestamp, tool_name, tool_args = obj.tool_calls[-1]
            if hasattr(tool_args, "items"):
                args_str = ", ".join(f"{k}={v}" for k, v in tool_args.items())
            else:
                args_str = str(tool_args)
            with open(log_file, "a", encoding=encoding, errors=errors) as file_obj:
                file_obj.write(f"{timestamp} [Tool Call] {tool_name}({args_str})\n")

        return wrapper

    def save_report_section_decorator(obj, func_name):
        func = getattr(obj, func_name)

        @wraps(func)
        def wrapper(section_name, content):
            func(section_name, content)
            if section_name in obj.report_sections and obj.report_sections[section_name] is not None:
                section_content = obj.report_sections[section_name]
                if section_content:
                    file_name = f"{section_name}.md"
                    text = (
                        "\n".join(str(item) for item in section_content)
                        if isinstance(section_content, list)
                        else str(section_content)
                    )
                    with open(
                        report_dir / file_name,
                        "w",
                        encoding=encoding,
                        errors=errors,
                    ) as file_obj:
                        file_obj.write(text)

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
        analyst_parts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "sentiment.md").write_text(
            final_state["sentiment_report"], encoding=encoding, errors=errors
        )
        analyst_parts.append(("Sentiment Analyst", final_state["sentiment_report"]))
    if final_state.get("news_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "news.md").write_text(
            final_state["news_report"], encoding=encoding, errors=errors
        )
        analyst_parts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("tokenomics_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "tokenomics.md").write_text(
            final_state["tokenomics_report"], encoding=encoding, errors=errors
        )
        analyst_parts.append(("Tokenomics Analyst", final_state["tokenomics_report"]))
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
            research_parts.append(("Bull Researcher", debate["bull_history"]))
        if debate.get("bear_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bear.md").write_text(
                debate["bear_history"], encoding=encoding, errors=errors
            )
            research_parts.append(("Bear Researcher", debate["bear_history"]))
        if debate.get("judge_decision"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "manager.md").write_text(
                debate["judge_decision"], encoding=encoding, errors=errors
            )
            research_parts.append(("Research Manager", debate["judge_decision"]))
        if research_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in research_parts)
            sections.append(f"## II. Research Team Decision\n\n{content}")

    if final_state.get("trader_investment_plan"):
        trading_dir = save_path / "3_trading"
        trading_dir.mkdir(exist_ok=True)
        (trading_dir / "trader.md").write_text(
            final_state["trader_investment_plan"], encoding=encoding, errors=errors
        )
        sections.append(
            "## III. Trading Team Plan\n\n### Trader\n"
            f"{final_state['trader_investment_plan']}"
        )

    if final_state.get("risk_debate_state"):
        risk_dir = save_path / "4_risk"
        risk = final_state["risk_debate_state"]
        risk_parts = []
        if risk.get("aggressive_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "aggressive.md").write_text(
                risk["aggressive_history"], encoding=encoding, errors=errors
            )
            risk_parts.append(("Aggressive Analyst", risk["aggressive_history"]))
        if risk.get("conservative_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "conservative.md").write_text(
                risk["conservative_history"], encoding=encoding, errors=errors
            )
            risk_parts.append(("Conservative Analyst", risk["conservative_history"]))
        if risk.get("neutral_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "neutral.md").write_text(
                risk["neutral_history"], encoding=encoding, errors=errors
            )
            risk_parts.append(("Neutral Analyst", risk["neutral_history"]))
        if risk_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in risk_parts)
            sections.append(f"## IV. Risk Management Team Decision\n\n{content}")

        if risk.get("judge_decision"):
            portfolio_dir = save_path / "5_portfolio"
            portfolio_dir.mkdir(exist_ok=True)
            (portfolio_dir / "decision.md").write_text(
                risk["judge_decision"], encoding=encoding, errors=errors
            )
            sections.append(
                "## V. Portfolio Manager Decision\n\n### Portfolio Manager\n"
                f"{risk['judge_decision']}"
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
        analysts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analysts.append(("Sentiment Analyst", final_state["sentiment_report"]))
    if final_state.get("news_report"):
        analysts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("tokenomics_report"):
        analysts.append(("Tokenomics Analyst", final_state["tokenomics_report"]))
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
            research.append(("Bull Researcher", debate["bull_history"]))
        if debate.get("bear_history"):
            research.append(("Bear Researcher", debate["bear_history"]))
        if debate.get("judge_decision"):
            research.append(("Research Manager", debate["judge_decision"]))
        if research:
            console.print(
                Panel("[bold]II. Research Team Decision[/bold]", border_style="magenta")
            )
            for title, content in research:
                console.print(
                    Panel(Markdown(content), title=title, border_style="blue", padding=(1, 2))
                )

    if final_state.get("trader_investment_plan"):
        console.print(Panel("[bold]III. Trading Team Plan[/bold]", border_style="yellow"))
        console.print(
            Panel(
                Markdown(final_state["trader_investment_plan"]),
                title="Trader",
                border_style="blue",
                padding=(1, 2),
            )
        )

    if final_state.get("risk_debate_state"):
        risk = final_state["risk_debate_state"]
        risk_reports = []
        if risk.get("aggressive_history"):
            risk_reports.append(("Aggressive Analyst", risk["aggressive_history"]))
        if risk.get("conservative_history"):
            risk_reports.append(("Conservative Analyst", risk["conservative_history"]))
        if risk.get("neutral_history"):
            risk_reports.append(("Neutral Analyst", risk["neutral_history"]))
        if risk_reports:
            console.print(
                Panel(
                    "[bold]IV. Risk Management Team Decision[/bold]",
                    border_style="red",
                )
            )
            for title, content in risk_reports:
                console.print(
                    Panel(Markdown(content), title=title, border_style="blue", padding=(1, 2))
                )

        if risk.get("judge_decision"):
            console.print(
                Panel("[bold]V. Portfolio Manager Decision[/bold]", border_style="green")
            )
            console.print(
                Panel(
                    Markdown(risk["judge_decision"]),
                    title="Portfolio Manager",
                    border_style="blue",
                    padding=(1, 2),
                )
            )
