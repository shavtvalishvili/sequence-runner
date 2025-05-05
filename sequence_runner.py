import inspect
import json
import os
from json import JSONDecodeError

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.graph import CompiledGraph
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool

from mcp import ClientSession
from mcp.client.sse import sse_client

from mock_db import SEQUENCES, AGENTS, CLIENT_CONFIGS
from schema_factory import SchemaFactory
from session_state import SessionState
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from jsonschema_pydantic import jsonschema_to_pydantic

load_dotenv()


class SequenceRunner:
    def __init__(self, sequence_id: str, client_id: str, product_id: str, initial_state=None):
        if initial_state is None:
            initial_state = {}
        self.sequence_id = sequence_id
        self.client_id = client_id
        self.product_id = product_id
        self.sequence = None
        self.client_config = None
        self.graph = StateGraph(SessionState)
        self.schema_factory = SchemaFactory()
        self.initial_state = initial_state

    async def load_configurations(self):
        self.sequence = SEQUENCES.get(self.sequence_id)
        if not self.sequence:
            raise ValueError(f"Sequence {self.sequence_id} not found")
        self.client_config = CLIENT_CONFIGS.get(self.client_id, {})

    @staticmethod
    def check_skip_conditions(step: dict, state: SessionState) -> bool:
        skip_conditions = step.get("skip_conditions", {})
        for key, value in skip_conditions.items():
            print("Checking skip condition:", key, value)
            if state.get(key) == value:
                return True
        return False

    def assemble_graph(self, tools):
        previous_step_id = START
        for i, current_step in enumerate(self.sequence["steps"]):
            step_id = current_step["id"]

            def make_step_function(step, _tools):
                async def step_function(state):
                    if self.check_skip_conditions(step, state):
                        return state

                    if step["type"] == "tool":
                        step_tool = next((t for t in _tools if t.name == step["id"]), None)
                        if not tool:
                            raise ValueError(f"Tool {step['id']} not found")

                        if hasattr(step_tool, "ainvoke"):
                            result = await step_tool.ainvoke(state)
                        elif inspect.iscoroutinefunction(step_tool.invoke):
                            result = await step_tool.invoke(state)
                        else:
                            result = step_tool.invoke(state)
                        try:
                            result = json.loads(result)
                        except JSONDecodeError as e:
                            print("Couldn't decode the result as JSON:", e)

                    elif step["type"] == "agent":
                        agent, messages = self.create_llm_agent(
                            step["id"], _tools, state
                        )
                        # ToDo: Failed API call handling
                        result = (await agent.ainvoke({'messages': messages}))['structured_response']
                        result = result.dict() if hasattr(result, 'dict') else result

                    else:
                        raise ValueError(f"Unknown step type: {step['type']}")

                    # If an output key is present in the step config, write the result to that key in state
                    # Else if a result is a dict, update the state with the result
                    # Else, write the result under "<step_id>_result" key inside the state
                    output_key = step.get("output_key")
                    print("BEFORE", state, '\n')
                    if output_key:
                        state[output_key] = result
                    elif isinstance(result, dict):
                        state.update(result)
                    else:
                        state[f"{step['id']}_result"] = result
                    print("AFTER", state, '\n')

                    return state

                return step_function

            self.graph.add_node(step_id, make_step_function(current_step, tools))
            self.graph.add_edge(previous_step_id, step_id)
            previous_step_id = step_id

        self.graph.add_edge(previous_step_id, END)

    def create_llm_agent(self, agent_id: str, all_tools, state) -> (CompiledGraph, list[BaseMessage]):
        agent_config = AGENTS.get(agent_id)
        if not agent_config:
            raise ValueError(f"Agent {agent_id} not found")

        prompt_messages = self.fill_up_prompt(agent_config["prompt"], state, agent_id)
        tools = self.gather_tools(agent_config.get("tools", []), all_tools, agent_id)
        sub_agents = self.gather_sub_agents(agent_config.get("sub-agents", []), all_tools, state)
        OutputSchema = jsonschema_to_pydantic(json.loads(agent_config["output-schema"]))
        model = init_chat_model(
            agent_config["model"],
            temperature=0,
        )

        return create_react_agent(model=model, tools=tools + sub_agents, response_format=OutputSchema), prompt_messages

    def create_llm_agent_tool(self, aid, all_tools, state: dict):
        child_agent, messages = self.create_llm_agent(aid, all_tools, state)

        @tool
        def agent_as_tool() -> dict:
            result = child_agent.invoke({'messages': messages})
            return result

        return child_agent

    @staticmethod
    def gather_tools(tool_names: list[str], all_tools, parent_agent_id: str) -> list:
        gathered = []
        for name in tool_names:
            required_tool = next((t for t in all_tools if t.name == name), None)
            if not tool:
                raise ValueError(f"Tool {name} not found for agent {parent_agent_id}")
            gathered.append(required_tool)
        return gathered

    def gather_sub_agents(self, sub_agents: list[str], all_tools, state: dict) -> list:
        gathered = []
        for agent_id in sub_agents:
            gathered.append(self.create_llm_agent_tool(agent_id, all_tools, state))
        return gathered

    def fill_up_prompt(self, prompt_message_list: str, state: SessionState, agent_id: str) -> list[BaseMessage]:
        # ToDo: Implement support for MessagesPlaceholder(variable_name="conversation_history") insert inside
        # prompt_message_list for passing in a dynamic list of user messages
        chat_prompt_template = ChatPromptTemplate.from_messages(prompt_message_list)
        try:
            context = {**self.client_config, **state}
            return chat_prompt_template.format_messages(**context)
        except KeyError as e:
            raise ValueError(f"Missing key {e} in context for agent {agent_id}")

    def flatten_dict(self, dictionary, parent_key='', sep='.'):
        items = {}
        for k, v in dictionary.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(self.flatten_dict(v, new_key, sep=sep))
            else:
                items[new_key] = v
        return items

    async def run_sequence_async(self):
        async with sse_client(os.environ.get("MCP_SERVER_URL")) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await load_mcp_tools(session)
                self.assemble_graph(tools)
                compiled_graph = self.graph.compile()
                await compiled_graph.ainvoke(self.initial_state)
