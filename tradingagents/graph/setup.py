# TradingAgents/graph/setup.py

from typing import Any, Dict
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    ANALYST_ALIASES = {
        "sentiment": "volume_flow",
        "sentiment_analyst": "volume_flow",
        "volume_flow_analyst": "volume_flow",
        "funding_oi_analyst": "funding_oi",
        "funding": "funding_oi",
        "oi": "funding_oi",
        "derivatives": "funding_oi",
        "derivatives_analyst": "funding_oi",
        "catalyst_news": "news",
        "catalyst_news_analyst": "news",
        "event_news": "news",
        "event_news_analyst": "news",
        "market_structure": "market",
        "market_structure_analyst": "market",
        "tokenomics_onchain": "tokenomics",
        "tokenomics_onchain_analyst": "tokenomics",
    }

    ANALYST_NODE_NAMES = {
        "market": "Market Structure Analyst",
        "volume_flow": "Volume Flow Analyst",
        "funding_oi": "Funding & OI Analyst",
        "news": "News Analyst",
        "tokenomics": "Tokenomics & On-Chain Analyst",
    }

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        bull_memory,
        bear_memory,
        trader_memory,
        invest_judge_memory,
        conditional_logic: ConditionalLogic,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.conditional_logic = conditional_logic

    def _normalize_selected_analysts(self, selected_analysts):
        normalized = []
        for analyst in selected_analysts:
            analyst_key = self.ANALYST_ALIASES.get(
                str(analyst).strip().lower(),
                str(analyst).strip().lower(),
            )
            if analyst_key not in normalized:
                normalized.append(analyst_key)
        return normalized

    def _clear_node_name(self, analyst_type: str) -> str:
        if analyst_type == "volume_flow":
            return "Msg Clear Volume Flow"
        if analyst_type == "funding_oi":
            return "Msg Clear Funding Oi"
        return f"Msg Clear {analyst_type.capitalize()}"

    def setup_graph(
        self, selected_analysts=["market", "volume_flow", "funding_oi", "news", "tokenomics"]
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market structure analyst
                - "volume_flow": Volume flow analyst
                - "funding_oi": Funding and open interest analyst
                - "news": News analyst
                - "tokenomics": Tokenomics and on-chain analyst
        """
        selected_analysts = self._normalize_selected_analysts(selected_analysts)
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Create analyst nodes
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        if "market" in selected_analysts:
            analyst_nodes["market"] = create_market_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["market"] = create_msg_delete()
            tool_nodes["market"] = self.tool_nodes["market"]

        if "volume_flow" in selected_analysts:
            analyst_nodes["volume_flow"] = create_volume_flow_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["volume_flow"] = create_msg_delete()
            tool_nodes["volume_flow"] = self.tool_nodes["volume_flow"]

        if "funding_oi" in selected_analysts:
            analyst_nodes["funding_oi"] = create_funding_oi_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["funding_oi"] = create_msg_delete()
            tool_nodes["funding_oi"] = self.tool_nodes["funding_oi"]

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["news"] = create_msg_delete()
            tool_nodes["news"] = self.tool_nodes["news"]

        if "tokenomics" in selected_analysts:
            analyst_nodes["tokenomics"] = create_tokenomics_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["tokenomics"] = create_msg_delete()
            tool_nodes["tokenomics"] = self.tool_nodes["tokenomics"]

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(
            self.quick_thinking_llm, self.bull_memory
        )
        bear_researcher_node = create_bear_researcher(
            self.quick_thinking_llm, self.bear_memory
        )
        research_manager_node = create_research_manager(
            self.deep_thinking_llm, self.invest_judge_memory
        )
        setup_classifier_node = create_setup_classifier(self.quick_thinking_llm)
        decision_engine_node = create_decision_engine(self.quick_thinking_llm)
        execution_node = create_trader(self.quick_thinking_llm, self.trader_memory)

        # Create risk analysis nodes
        trade_risk_analyst = create_trade_risk_analyst(self.quick_thinking_llm)
        portfolio_risk_analyst = create_portfolio_risk_analyst(self.quick_thinking_llm)

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for analyst_type, node in analyst_nodes.items():
            analyst_name = self.ANALYST_NODE_NAMES[analyst_type]
            workflow.add_node(analyst_name, node)
            workflow.add_node(self._clear_node_name(analyst_type), delete_nodes[analyst_type])
            workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # Add other nodes
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Setup Classifier", setup_classifier_node)
        workflow.add_node("Decision Engine", decision_engine_node)
        workflow.add_node("Execution Team", execution_node)
        workflow.add_node("Trade Risk Analyst", trade_risk_analyst)
        workflow.add_node("Portfolio Risk Analyst", portfolio_risk_analyst)

        # Define edges
        # Start with the first analyst
        first_analyst = selected_analysts[0]
        workflow.add_edge(START, self.ANALYST_NODE_NAMES[first_analyst])

        # Connect analysts in sequence
        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = self.ANALYST_NODE_NAMES[analyst_type]
            current_tools = f"tools_{analyst_type}"
            current_clear = self._clear_node_name(analyst_type)

            # Add conditional edges for current analyst
            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            # Connect to next analyst or to Bull Researcher if this is the last analyst
            if i < len(selected_analysts) - 1:
                next_analyst = self.ANALYST_NODE_NAMES[selected_analysts[i + 1]]
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_edge(current_clear, "Bull Researcher")

        # Add remaining edges
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_edge("Research Manager", "Setup Classifier")
        workflow.add_edge("Setup Classifier", "Decision Engine")
        workflow.add_edge("Decision Engine", "Trade Risk Analyst")
        workflow.add_edge("Trade Risk Analyst", "Portfolio Risk Analyst")
        workflow.add_edge("Portfolio Risk Analyst", "Execution Team")
        workflow.add_edge("Execution Team", END)

        # Compile and return
        return workflow.compile()
