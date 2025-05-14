import asyncio
from typing import Any


class ToolInvoker:
    @staticmethod
    async def invoke(step_tool: Any, tool_context: dict) -> Any:
        # Async entrypoint
        if callable(getattr(step_tool, "ainvoke", None)):
            return await step_tool.ainvoke(tool_context)

        # Legacy async entrypoint
        if callable(getattr(step_tool, "arun", None)):
            return await step_tool.arun(**tool_context)

        # Coroutine-style invoke
        invoke = getattr(step_tool, "invoke", None)
        if invoke and asyncio.iscoroutinefunction(invoke):
            return await invoke(tool_context)

        # Sync invoke
        if invoke:
            return invoke(tool_context)

        raise AttributeError(f"Tool {step_tool!r} has no ainvoke/arun/invoke")