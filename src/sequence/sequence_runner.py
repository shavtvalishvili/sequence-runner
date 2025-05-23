from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph.graph import CompiledGraph
from mcp import ClientSession
from mcp.client.stdio import stdio_client

from src.agent.agent_factory import AgentFactory
from src.graph.graph_builder import GraphBuilder
from src.sequence.sequence_config_loader import SequenceConfigLoader
from src.tools.constants import SERVER_PARAMETERS
from src.tools.tool_invoker import ToolInvoker


class SequenceRunner:
    def __init__(
            self,
            sequence_id: str,
            client_id: str,
            product_id: str,
            initial_state: dict = None,
    ):
        if initial_state is None:
            initial_state = {}
        self.sequence_id = sequence_id
        self.client_id = client_id
        self.product_id = product_id
        self.initial_state = initial_state
        self.final_state = None

        # injected collaborators
        self.config_loader = SequenceConfigLoader()
        self.tool_invoker = ToolInvoker()
        self.agent_factory = None
        self.graph_builder = None

        self.sequence = {}
        self.client_config = {}
        self.all_agents = {}

    async def load_configurations(self):
        """
        Loads sequence, client_config, and agents from the DB.
        Must be called before run_sequence_async().
        """
        self.sequence = self.config_loader.load_sequence(self.sequence_id)
        self.client_config = self.config_loader.load_client_config(self.client_id)
        self.all_agents = self.config_loader.load_all_agents()

        self.agent_factory = AgentFactory(self.all_agents, self.client_config)
        self.graph_builder = GraphBuilder(self.tool_invoker, self.agent_factory, self.client_config)

    async def run_sequence_async(self):
        """
        Builds the graph for the previously-loaded sequence, compiles it,
        then invokes it with the initial_state.
        """
        if len(self.sequence) == 0:
            raise RuntimeError("Must call load_configurations() first")

        # Guarantee to include client_id in the initial state
        self.initial_state.setdefault("client_id", self.client_id)

        # Open MCP session & load raw tools
        async with stdio_client(SERVER_PARAMETERS) as (r, w), ClientSession(r, w) as session:
            await session.initialize()
            mcp_tools = await load_mcp_tools(session)

            # Assemble & compile the graph
            graph = self.graph_builder.build(self.sequence, mcp_tools)
            compiled: CompiledGraph = graph.compile()

            # Kick off the sequence
            self.final_state = await compiled.ainvoke(self.initial_state)

            return self.final_state
