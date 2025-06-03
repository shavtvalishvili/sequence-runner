import os
import sys

from mcp import StdioServerParameters

env = os.environ.copy()
env["PYTHONPATH"] = (
    os.environ.get("LAMBDA_TASK_ROOT", "") + ":" + env.get("PYTHONPATH", "")
)

SERVER_PARAMETERS = StdioServerParameters(
    command=f"{sys.executable}", args=["mcp-server/server.py"], env=env
)
