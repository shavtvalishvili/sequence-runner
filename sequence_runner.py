import asyncio
import json
import os
from json import JSONDecodeError
from typing import Any

from dotenv import load_dotenv
from google.adk.tools import BaseTool
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.graph import CompiledGraph
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool, StructuredTool

from mcp import ClientSession
from mcp.client.sse import sse_client

from mock_db import SEQUENCES, AGENTS, CLIENT_CONFIGS
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
        self.initial_state = initial_state
        self.all_agents = {}

    async def load_configurations(self):
        # Load sequence, client and agent configurations from the database or any other source
        self.sequence = SEQUENCES.get(self.sequence_id)
        if not self.sequence:
            raise ValueError(f"Sequence {self.sequence_id} not found")
        self.client_config = CLIENT_CONFIGS.get(self.client_id, {})
        self.all_agents = AGENTS

    @staticmethod
    def check_skip_conditions(step: dict, state: SessionState) -> bool:
        skip_conditions = step.get("skip_conditions", {})
        for key, value in skip_conditions.items():
            print("Checking skip condition:", key, value)
            if state.get(key) == value:
                return True
        return False

    @staticmethod
    async def call_tool(step_tool, tool_context):
        # 1. If they’ve got ainvoke(), use it
        ainvoke = getattr(step_tool, "ainvoke", None)
        if callable(ainvoke):
            return await ainvoke(tool_context)

        # 2. Otherwise, if they’ve got an arun(), use it (some tools use arun)
        arun = getattr(step_tool, "arun", None)
        if callable(arun):
            # arun typically takes **kwargs, not a single dict
            if isinstance(tool_context, dict):
                return await arun(**tool_context)
            else:
                # fallback if a tool expects a single positional
                return await arun(tool_context)

        # 3. Otherwise, if invoke is itself a coroutine function, await it
        invoke = getattr(step_tool, "invoke", None)
        if invoke and asyncio.iscoroutinefunction(invoke):
            return await invoke(tool_context)

        # 4. Finally, fall back to sync .invoke()
        if invoke:
            return invoke(tool_context)

        raise AttributeError("Tool has no ainvoke, arun, or invoke")

    def assemble_graph(self, tools: list[BaseTool]):
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

                        tool_context = self.get_step_context(step, state)
                        result = await self.call_tool(step_tool, tool_context)

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
        agent_config = self.all_agents.get(agent_id)
        if not agent_config:
            raise ValueError(f"Agent {agent_id} not found")

        optional_default_values = {}
        required_default_values = {}
        for dependency in agent_config.get("dependencies", []):
            key = dependency["key"]
            if dependency.get("default_value") is not None and dependency.get("override"):
                required_default_values[key] = dependency["default_value"]
            elif dependency.get("default_value") is not None:
                optional_default_values[key] = dependency["default_value"]

        context = self.get_step_context(agent_config, state)
        context = {**optional_default_values, **context, **required_default_values}

        prompt_messages = self.fill_up_prompt(agent_config, context, agent_id)
        tools = self.gather_tools(agent_config.get("tools", []), all_tools, context, agent_id)
        sub_agents = self.gather_sub_agents(agent_config.get("sub-agents", []), all_tools, context)
        OutputSchema = jsonschema_to_pydantic(json.loads(agent_config["output-schema"]))
        model = init_chat_model(
            agent_config["model"],
            temperature=0,
        )

        return create_react_agent(model=model, tools=tools + sub_agents, response_format=OutputSchema, ), prompt_messages

    def create_llm_agent_tool(self, agent_id, all_tools, context: dict):
        child_agent, messages = self.create_llm_agent(agent_id, all_tools, context)

        # ToDo: Support all outputs from the agent
        # ToDo: Something's weird
        @tool(description=f"Agent tool wrapper for {agent_id}")
        def agent_as_tool(**tool_kwargs) -> Any:
            merged_context = {**tool_kwargs, **context}
            result = child_agent.invoke({
                'messages': messages,
                **merged_context,
            })
            return result

        child_agent.name = agent_id

        return child_agent

    @staticmethod
    def gather_tools(tool_names: list[str], all_tools, context: dict, parent_agent_id: str) -> list:
        gathered: list[StructuredTool] = []

        for tool_name in tool_names:
            original_tool = next((t for t in all_tools if t.name == tool_name), None)
            if not original_tool:
                raise ValueError(f"Tool {tool_name} not found for agent {parent_agent_id}")

            # Async wrapper
            async def _async_wrapper(**kwargs):
                merged = {**kwargs, **context}
                return await SequenceRunner.call_tool(original_tool, merged)

            # A sync shim that just drives the async wrapper
            def _run_shim(**kwargs):
                # Previous nest_asyncio.apply() call is necessary
                return asyncio.run(_async_wrapper(**kwargs))

            wrapped = StructuredTool.from_function(
                func=_run_shim,
                coroutine=_async_wrapper,
                name=original_tool.name,
                description=original_tool.description,
                args_schema=original_tool.args_schema,
            )

            gathered.append(wrapped)

        return gathered

    def gather_sub_agents(self, sub_agents: list[str], all_tools, context: dict) -> list:
        gathered = []
        for agent_id in sub_agents:
            gathered.append(self.create_llm_agent_tool(agent_id, all_tools, context))
        return gathered

    def get_step_context(self, step_config: dict, state: SessionState) -> dict:
        argument_overrides = {}
        for key, value in step_config.get("arguments", {}).items():
            if value["type"] == "dynamic":
                argument_overrides[key] = '{value["value"]}'.format_map(state)
            elif value["type"] == "static":
                argument_overrides[key] = value["value"]

        return {**self.client_config, **state, **argument_overrides}

    @staticmethod
    def fill_up_prompt(agent_config: dict, context: dict, agent_id: str) -> list[BaseMessage]:
        # ToDo: Implement support for MessagesPlaceholder(variable_name="conversation_history") insert inside
        # prompt_message_list for passing in a dynamic list of user messages
        prompt_message_list = agent_config["prompt"]
        chat_prompt_template = ChatPromptTemplate.from_messages(prompt_message_list)

        try:
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
