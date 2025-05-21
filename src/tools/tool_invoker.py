import asyncio
from typing import Any


class ToolInvoker:
    @staticmethod
    async def invoke(step_tool: Any, tool_context: dict) -> Any:
        # Filter the tool_context to only include keys that are in step_tool.args_schema
        filtered_context = {key: value for key, value in tool_context.items() if key in step_tool.args.keys()}

        # Async entrypoint
        if callable(getattr(step_tool, "ainvoke", None)):
            return await step_tool.ainvoke(filtered_context)

        # Legacy async entrypoint
        if callable(getattr(step_tool, "arun", None)):
            return await step_tool.arun(**filtered_context)

        # Coroutine-style invoke
        invoke = getattr(step_tool, "invoke", None)
        if invoke and asyncio.iscoroutinefunction(invoke):
            return await invoke(filtered_context)

        # Sync invoke
        if invoke:
            return invoke(filtered_context)

        raise AttributeError(f"Tool {step_tool!r} has no ainvoke/arun/invoke")
