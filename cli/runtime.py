import ast


ANALYST_ORDER = ["market", "volume_flow", "funding_oi", "news", "tokenomics"]
ANALYST_AGENT_NAMES = {
    "market": "Market Structure Analyst",
    "volume_flow": "Volume Flow Analyst",
    "funding_oi": "Funding & OI Analyst",
    "news": "News Analyst",
    "tokenomics": "Tokenomics & On-Chain Analyst",
}
ANALYST_REPORT_MAP = {
    "market": "market_report",
    "volume_flow": "sentiment_report",
    "funding_oi": "funding_oi_report",
    "news": "news_report",
    "tokenomics": "tokenomics_report",
}
RESEARCH_AGENT_NAMES = [
    "Bull Researcher",
    "Bear Researcher",
    "Research Manager",
]
DECISION_AGENT_NAMES = ["Setup Classifier", "Decision Engine"]
RISK_AGENT_NAMES = ["Trade Risk Analyst", "Portfolio Risk Analyst"]
EXECUTION_AGENT_NAMES = ["Execution Team"]
POST_RESEARCH_AGENT_NAMES = [
    "Setup Classifier",
    "Decision Engine",
    "Trade Risk Analyst",
    "Portfolio Risk Analyst",
    "Execution Team",
]
POST_DECISION_AGENT_NAMES = [
    "Trade Risk Analyst",
    "Portfolio Risk Analyst",
    "Execution Team",
]
POST_RISK_AGENT_NAMES = [
    "Execution Team",
]
POST_TRADE_RISK_AGENT_NAMES = [
    "Portfolio Risk Analyst",
    "Execution Team",
]
POST_PORTFOLIO_RISK_AGENT_NAMES = [
    "Execution Team",
]
POST_EXECUTION_AGENT_NAMES = []

# Backward-compatible aliases for older imports/tests.
POST_TRADER_AGENT_NAMES = POST_EXECUTION_AGENT_NAMES


def _set_status_if_known(message_buffer, agent_name, status):
    if agent_name in message_buffer.agent_status:
        message_buffer.update_agent_status(agent_name, status)


def set_agent_group_pending(message_buffer, agent_names):
    for agent_name in agent_names:
        if message_buffer.agent_status.get(agent_name) != "completed":
            _set_status_if_known(message_buffer, agent_name, "pending")


def _resolve_debate_status(has_history, is_done, is_next_speaker):
    if is_done:
        return "completed"
    if is_next_speaker:
        return "in_progress"
    if has_history:
        return "waiting"
    return "pending"


def update_analyst_statuses(message_buffer, chunk):
    selected = message_buffer.selected_analysts
    found_active = False

    for analyst_key in ANALYST_ORDER:
        if analyst_key not in selected:
            continue

        agent_name = ANALYST_AGENT_NAMES[analyst_key]
        report_key = ANALYST_REPORT_MAP[analyst_key]

        if chunk.get(report_key):
            message_buffer.update_report_section(report_key, chunk[report_key])

        has_report = bool(message_buffer.report_sections.get(report_key))

        if has_report:
            message_buffer.update_agent_status(agent_name, "completed")
        elif not found_active:
            message_buffer.update_agent_status(agent_name, "in_progress")
            found_active = True
        else:
            message_buffer.update_agent_status(agent_name, "pending")


def analysts_phase_completed(message_buffer):
    selected = message_buffer.selected_analysts
    if not selected:
        return False

    return all(
        message_buffer.agent_status.get(ANALYST_AGENT_NAMES[analyst_key]) == "completed"
        for analyst_key in selected
    )


def research_phase_completed(message_buffer):
    return message_buffer.agent_status.get("Research Manager") == "completed"


def execution_phase_completed(message_buffer):
    return message_buffer.agent_status.get("Execution Team") == "completed"


def trader_phase_completed(message_buffer):
    return execution_phase_completed(message_buffer)


def trade_risk_phase_completed(message_buffer):
    return message_buffer.agent_status.get("Trade Risk Analyst") == "completed"


def portfolio_risk_phase_completed(message_buffer):
    return message_buffer.agent_status.get("Portfolio Risk Analyst") == "completed"


def decision_phase_completed(message_buffer):
    return message_buffer.agent_status.get("Decision Engine") == "completed"


def update_research_debate_statuses(message_buffer, debate_state, max_rounds):
    bull_history = (debate_state.get("bull_history") or "").strip()
    bear_history = (debate_state.get("bear_history") or "").strip()
    judge_decision = (debate_state.get("judge_decision") or "").strip()
    current_response = (debate_state.get("current_response") or "").strip()
    count = max(0, int(debate_state.get("count") or 0))
    total_turns = max(1, int(max_rounds)) * 2

    next_speaker = None
    if not judge_decision:
        if count >= total_turns:
            next_speaker = "Research Manager"
        elif current_response.startswith("Bull"):
            next_speaker = "Bear Researcher"
        else:
            next_speaker = "Bull Researcher"

    bull_done = bool(bull_history) and (bool(judge_decision) or count >= total_turns - 1)
    bear_done = bool(bear_history) and (bool(judge_decision) or count >= total_turns)

    statuses = {
        "Bull Researcher": _resolve_debate_status(
            has_history=bool(bull_history),
            is_done=bull_done,
            is_next_speaker=next_speaker == "Bull Researcher",
        ),
        "Bear Researcher": _resolve_debate_status(
            has_history=bool(bear_history),
            is_done=bear_done,
            is_next_speaker=next_speaker == "Bear Researcher",
        ),
        "Research Manager": (
            "completed"
            if judge_decision
            else "in_progress"
            if next_speaker == "Research Manager"
            else "pending"
        ),
    }

    for agent_name, status in statuses.items():
        _set_status_if_known(message_buffer, agent_name, status)


def extract_content_string(content):
    def is_empty(val):
        if val is None or val == "":
            return True
        if isinstance(val, str):
            text = val.strip()
            if not text:
                return True
            try:
                return not bool(ast.literal_eval(text))
            except (ValueError, SyntaxError):
                return False
        return not bool(val)

    if is_empty(content):
        return None

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, dict):
        text = content.get("text", "")
        return text.strip() if not is_empty(text) else None

    if isinstance(content, list):
        text_parts = [
            item.get("text", "").strip()
            if isinstance(item, dict) and item.get("type") == "text"
            else (item.strip() if isinstance(item, str) else "")
            for item in content
        ]
        result = " ".join(t for t in text_parts if t and not is_empty(t))
        return result if result else None

    return str(content).strip() if not is_empty(content) else None


def classify_message_type(message) -> tuple[str, str | None]:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    content = extract_content_string(getattr(message, "content", None))

    if isinstance(message, HumanMessage):
        if content and content.strip() == "Continue":
            return ("Control", content)
        return ("User", content)

    if isinstance(message, ToolMessage):
        return ("Data", content)

    if isinstance(message, AIMessage):
        return ("Agent", content)

    return ("System", content)
