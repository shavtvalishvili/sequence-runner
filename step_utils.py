from session_state import SessionState


def check_skip_conditions(step: dict, state: SessionState) -> bool:
    for key, value in step.get("skip_conditions", {}).items():
        if state.get(key) == value:
            return True
    return False

def get_step_context_static(step_cfg: dict, state: SessionState, client_cfg: dict) -> dict:
    overrides = {}
    for key, value in step_cfg.get("arguments", {}).items():
        if value["type"] == "dynamic":
            overrides[key] = '{value["value"]}'.format_map(state)
        elif value["type"] == "static":
            overrides[key] = value["value"]
    return {**client_cfg, **state, **overrides}