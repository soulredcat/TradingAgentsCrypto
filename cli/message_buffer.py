import datetime
from collections import deque


class MessageBuffer:
    # Fixed teams that always run (not user-selectable)
    FIXED_AGENTS = {
        "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
        "Decision Team": ["Setup Classifier", "Decision Engine"],
        "Risk Management": [
            "Trade Risk Analyst",
            "Portfolio Risk Analyst",
        ],
        "Execution Team": ["Execution Team"],
    }

    # Analyst name mapping
    ANALYST_MAPPING = {
        "market": "Market Structure Analyst",
        "volume_flow": "Volume Flow Analyst",
        "funding_oi": "Funding & OI Analyst",
        "news": "News Analyst",
        "tokenomics": "Tokenomics & On-Chain Analyst",
    }

    # Report section mapping: section -> (analyst_key for filtering, finalizing_agent)
    REPORT_SECTIONS = {
        "market_report": ("market", "Market Structure Analyst"),
        "sentiment_report": ("volume_flow", "Volume Flow Analyst"),
        "funding_oi_report": ("funding_oi", "Funding & OI Analyst"),
        "news_report": ("news", "News Analyst"),
        "tokenomics_report": ("tokenomics", "Tokenomics & On-Chain Analyst"),
        "investment_plan": (None, "Research Manager"),
        "setup_classification": (None, "Setup Classifier"),
        "decision_plan": (None, "Decision Engine"),
        "trader_investment_plan": (None, "Execution Team"),
        "trade_risk_assessment": (None, "Trade Risk Analyst"),
        "portfolio_risk_assessment": (None, "Portfolio Risk Analyst"),
    }

    def __init__(self, max_length=100):
        self.messages = deque(maxlen=max_length)
        self.tool_calls = deque(maxlen=max_length)
        self.current_report = None
        self.final_report = None
        self.agent_status = {}
        self.current_agent = None
        self.report_sections = {}
        self.selected_analysts = []
        self._processed_message_ids = set()

    def init_for_analysis(self, selected_analysts):
        self.selected_analysts = [a.lower() for a in selected_analysts]
        self.agent_status = {}

        for analyst_key in self.selected_analysts:
            if analyst_key in self.ANALYST_MAPPING:
                self.agent_status[self.ANALYST_MAPPING[analyst_key]] = "pending"

        for team_agents in self.FIXED_AGENTS.values():
            for agent in team_agents:
                self.agent_status[agent] = "pending"

        self.report_sections = {}
        for section, (analyst_key, _) in self.REPORT_SECTIONS.items():
            if analyst_key is None or analyst_key in self.selected_analysts:
                self.report_sections[section] = None

        self.current_report = None
        self.final_report = None
        self.current_agent = None
        self.messages.clear()
        self.tool_calls.clear()
        self._processed_message_ids.clear()

    def get_completed_reports_count(self):
        count = 0
        for section in self.report_sections:
            if section not in self.REPORT_SECTIONS:
                continue
            _, finalizing_agent = self.REPORT_SECTIONS[section]
            has_content = self.report_sections.get(section) is not None
            agent_done = self.agent_status.get(finalizing_agent) == "completed"
            if has_content and agent_done:
                count += 1
        return count

    def add_message(self, message_type, content):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.messages.append((timestamp, message_type, content))

    def add_tool_call(self, tool_name, args):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.tool_calls.append((timestamp, tool_name, args))

    def update_agent_status(self, agent, status):
        if agent in self.agent_status:
            self.agent_status[agent] = status
            self.current_agent = agent

    def update_report_section(self, section_name, content):
        if section_name in self.report_sections:
            self.report_sections[section_name] = content
            self._update_current_report()

    def _update_current_report(self):
        latest_section = None
        latest_content = None

        for section, content in self.report_sections.items():
            if content is not None:
                latest_section = section
                latest_content = content

        if latest_section and latest_content:
            section_titles = {
                "market_report": "Market Structure Analysis",
                "sentiment_report": "Volume Flow Analysis",
                "funding_oi_report": "Funding & OI Analysis",
                "news_report": "News Catalyst Analysis",
                "tokenomics_report": "Tokenomics & On-Chain Analysis",
                "investment_plan": "Research Team Verdict",
                "setup_classification": "Decision Team Setup Classification",
                "decision_plan": "Decision Team Formal Decision",
                "trader_investment_plan": "Execution Team Plan",
                "trade_risk_assessment": "Risk Management Trade Risk Assessment",
                "portfolio_risk_assessment": "Risk Management Portfolio Risk Assessment",
            }
            self.current_report = (
                f"### {section_titles[latest_section]}\n{latest_content}"
            )

        self._update_final_report()

    def _update_final_report(self):
        report_parts = []

        analyst_sections = [
            "market_report",
            "sentiment_report",
            "funding_oi_report",
            "news_report",
            "tokenomics_report",
        ]
        if any(self.report_sections.get(section) for section in analyst_sections):
            report_parts.append("## Analyst Team Reports")
            if self.report_sections.get("market_report"):
                report_parts.append(
                    "### Market Structure Analysis\n"
                    f"{self.report_sections['market_report']}"
                )
            if self.report_sections.get("sentiment_report"):
                report_parts.append(
                    "### Volume Flow Analysis\n"
                    f"{self.report_sections['sentiment_report']}"
                )
            if self.report_sections.get("funding_oi_report"):
                report_parts.append(
                    "### Funding & OI Analysis\n"
                    f"{self.report_sections['funding_oi_report']}"
                )
            if self.report_sections.get("news_report"):
                report_parts.append(
                    "### News Catalyst Analysis\n"
                    f"{self.report_sections['news_report']}"
                )
            if self.report_sections.get("tokenomics_report"):
                report_parts.append(
                    "### Tokenomics & On-Chain Analysis\n"
                    f"{self.report_sections['tokenomics_report']}"
                )

        if self.report_sections.get("investment_plan"):
            report_parts.append("## Research Team Verdict")
            report_parts.append(f"{self.report_sections['investment_plan']}")

        if self.report_sections.get("setup_classification"):
            report_parts.append("## Decision Team Setup Classification")
            report_parts.append(f"{self.report_sections['setup_classification']}")

        if self.report_sections.get("decision_plan"):
            report_parts.append("## Decision Team Formal Decision")
            report_parts.append(f"{self.report_sections['decision_plan']}")

        if self.report_sections.get("trade_risk_assessment"):
            report_parts.append("## Risk Management Trade Risk Assessment")
            report_parts.append(f"{self.report_sections['trade_risk_assessment']}")

        if self.report_sections.get("portfolio_risk_assessment"):
            report_parts.append("## Risk Management Portfolio Risk Assessment")
            report_parts.append(f"{self.report_sections['portfolio_risk_assessment']}")

        if self.report_sections.get("trader_investment_plan"):
            report_parts.append("## Execution Team Plan")
            report_parts.append(f"{self.report_sections['trader_investment_plan']}")

        self.final_report = "\n\n".join(report_parts) if report_parts else None
