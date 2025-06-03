from typing import Dict, List, Literal, NotRequired, TypedDict


# Argument value can be dynamic or static
class ArgumentValue(TypedDict):
    type: Literal["dynamic", "static"]
    value: str


# Arguments are a mapping from argument names to their values
Arguments = Dict[str, ArgumentValue]

# Skip conditions are a mapping from condition keys to boolean values
SkipConditions = Dict[str, bool]


# Step can be either an agent or a tool
class StepBase(TypedDict):
    type: Literal["agent", "tool"]
    id: str
    arguments: NotRequired[Arguments]
    skip_conditions: NotRequired[SkipConditions]
    output_key: NotRequired[str]


# Sequence consists of an ID and a list of steps
class Sequence(TypedDict):
    id: str
    steps: List[StepBase]
