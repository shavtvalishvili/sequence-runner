import json
from json import JSONDecodeError

from langchain_core.tools import BaseTool
from langgraph.constants import START, END
from langgraph.graph import StateGraph

from agent_factory import AgentFactory
from session_state import SessionState
from step_utils import check_skip_conditions, get_step_context_static
from tool_invoker import ToolInvoker


class GraphBuilder:
    def __init__(self, tool_invoker: ToolInvoker, agent_factory: AgentFactory, client_config: dict[str, dict]):
        self._invoker = tool_invoker
        self._agents = agent_factory
        self._client_config = client_config

    def build(self, sequence: dict, mcp_tools: list[BaseTool]) -> StateGraph:
        graph = StateGraph(SessionState)
        previous = START

        for step in sequence["steps"]:
            node_fn = self._make_node(step, mcp_tools)
            graph.add_node(step["id"], node_fn)
            graph.add_edge(previous, step["id"])
            previous = step["id"]

        graph.add_edge(previous, END)
        return graph

    def _make_node(self, step: dict, mcp_tools: list[BaseTool]):
        async def node(state: SessionState) -> SessionState:
            # Check skip conditions
            if check_skip_conditions(step, state):
                return state

            # Tool step
            if step["type"] == "tool":
                tool_obj = next((t for t in mcp_tools if t.name == step["id"]), None)
                if not tool_obj:
                    raise ValueError(f"Tool {step['id']} not found")
                ctx = get_step_context_static(step, state, self._client_config)
                raw = await self._invoker.invoke(tool_obj, ctx)

                try:
                    result = json.loads(raw)
                except (TypeError, JSONDecodeError):
                    result = raw

            # Agent step
            elif step["type"] == "agent":
                agent, msgs = self._agents.create_agent(step["id"], mcp_tools, state)
                # ToDo: Failed API call handling
                resp = await agent.ainvoke({"messages": msgs})
                structured = resp["structured_response"]
                result = structured.dict() if hasattr(structured, "dict") else structured

            else:
                raise ValueError(f"Unknown step type: {step['type']}")

            # Write back into state
            out_key = step.get("output_key")
            if out_key:
                state[out_key] = result
            elif isinstance(result, dict):
                state.update(result)
            else:
                state[f"{step['id']}_result"] = result

            return state

        return node
