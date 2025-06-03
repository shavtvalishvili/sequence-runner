from typing import Any

from src.sequence.types import Arguments, StepBase
from src.state.session_state import SessionState


def check_skip_conditions(step: StepBase, state: SessionState) -> bool:
    for key, value in step.get("skip_conditions", {}).items():
        if state.get(key) == value:
            return True
    return False


def get_step_context_static(
    arguments: Arguments, state: SessionState, client_cfg: dict[str, Any]
) -> dict:
    overrides = {}
    for key, value in arguments.items():
        if value["type"] == "dynamic":
            overrides[key] = f"{{{value['value']}}}".format_map(state)
        elif value["type"] == "static":
            overrides[key] = value["value"]
    return {**client_cfg, **state, **overrides}
