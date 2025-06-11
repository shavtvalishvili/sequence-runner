import asyncio
import json
from typing import Any

import pydantic
from jsonschema_pydantic import jsonschema_to_pydantic
from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import BaseTool, StructuredTool, tool
from langgraph.graph.graph import CompiledGraph
from langgraph.prebuilt import create_react_agent

from src.agent.types import Agent, Dependency
from src.sequence.step_utils import get_step_context_static
from src.sequence.types import Arguments
from src.state.session_state import SessionState
from src.tools.tool_invoker import ToolInvoker


class AgentFactory:
    def __init__(self, agents_config: dict[str, Agent], client_config: dict[str, Any]):
        self._configs = agents_config
        self._client_config = client_config

    def create_agent(
        self,
        agent_id: str,
        all_tools: list[BaseTool],
        state: SessionState,
        arguments: Arguments,
    ) -> tuple[CompiledGraph, list[BaseMessage]]:
        try:
            config = self._configs[agent_id]
        except:
            raise ValueError(f"Agent {agent_id} not found")

        # Build context defaults
        optional_defaults = {}
        required_defaults = {}
        for dep in config.get("dependencies", []):
            key = dep["key"]
            default = dep.get("default_value")
            if default is not None and dep.get("override"):
                required_defaults[key] = default
            elif default is not None:
                optional_defaults[key] = default

        base_context = get_step_context_static(arguments, state, self._client_config)
        context = {**optional_defaults, **base_context, **required_defaults}

        # Prompt messages
        prompt_list = config["prompt"]
        # ToDo: Implement support for MessagesPlaceholder(variable_name="conversation_history") insert inside
        # prompt_message_list for passing in a dynamic list of user messages
        chat_template = ChatPromptTemplate.from_messages(prompt_list)
        try:
            messages = chat_template.format_messages(**context)
        except KeyError as e:
            raise ValueError(f"Missing key {e} in context for agent {agent_id}")

        # Wrap tools & sub-agents
        wrapped_tools: list[StructuredTool] = []
        for tool_name in config.get("tools", []):
            wrapped_tools.append(self._wrap_tool(tool_name, all_tools, context))

        wrapped_sub_agents = [
            self.create_agent_tool(agent_id, all_tools, context, arguments)
            for agent_id in config.get("sub_agents", [])
        ]

        # Output schema & model
        OutputSchema = jsonschema_to_pydantic(json.loads(config["output_schema"]))
        model = init_chat_model(config["model"], temperature=0)

        react_agent = create_react_agent(
            model=model,
            tools=wrapped_tools + wrapped_sub_agents,
            response_format=OutputSchema,
        )

        return react_agent, messages

    def create_agent_tool(
        self,
        agent_id: str,
        all_tools: list[BaseTool],
        context: dict,
        arguments: Arguments,
    ) -> BaseTool:
        """
        Wraps a child agent as a sync/async tool, so it can be called
        as a sub-agent from another agent.
        """
        react_agent, messages = self.create_agent(
            agent_id, all_tools, context, arguments
        )
        try:
            config = self._configs[agent_id]
        except:
            raise ValueError(f"Agent {agent_id} not found")

        # ToDo: Make sure to support all outputs from the agent
        @tool(description=f"Sub-agent tool for {agent_id}")
        def sync_fn(**tool_kwargs: Any) -> Any:
            merged = {**tool_kwargs, **context}
            return react_agent.invoke(
                {
                    "messages": messages,
                    **merged,
                }
            )

        async def async_fn(**tool_kwargs: Any) -> Any:
            merged = {**tool_kwargs, **context}
            resp = await react_agent.ainvoke(
                {
                    "messages": messages,
                    **merged,
                }
            )
            structured_response = resp["structured_response"]
            return (
                # ToDo: .model_dump instead of .dict, duplicate code
                structured_response.dict()
                if hasattr(structured_response, "dict")
                else structured_response
            )

        input_fields: dict[str, Any] = {}
        dependencies: list[Dependency] = config["dependencies"]
        for item in dependencies:
            input_fields[item["key"]] = (Any, None)
        OutputSchema = pydantic.create_model(
            "DynamicInputSchema",
            **input_fields,
        )

        # Build a StructuredTool that supports both sync/async
        return StructuredTool.from_function(
            func=sync_fn,
            coroutine=async_fn,
            name=agent_id,
            description=f"Agent wrapper for {agent_id}",
            args_schema=OutputSchema,
        )

    @staticmethod
    def _wrap_tool(
        tool_name: str, all_tools: list[BaseTool], context: dict
    ) -> StructuredTool:
        original_tool = next(t for t in all_tools if t.name == tool_name)

        async def _async_wrapper(**kwargs: Any) -> Any:
            merged = {**kwargs, **context}
            return await ToolInvoker.invoke(original_tool, merged)

        def _sync(**kwargs: Any) -> Any:
            merged = {**kwargs, **context}
            return asyncio.run(_async_wrapper(**merged))

        return StructuredTool.from_function(
            func=_sync,
            coroutine=_async_wrapper,
            name=original_tool.name,
            description=original_tool.description,
            args_schema=original_tool.args_schema,
        )
