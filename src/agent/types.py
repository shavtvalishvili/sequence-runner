from typing import List, Literal, NotRequired, TypedDict


# Dependency specifies a key, default value, and override flag
class Dependency(TypedDict):
    key: str
    default_value: NotRequired[object]
    override: bool


# Prompt is a list of tuples with role and content
Prompt = List[tuple[Literal["system", "user"], str]]


# Agent definition includes various configurations
class Agent(TypedDict):
    id: str
    name: str
    model: str
    prompt: Prompt
    tools: List[str]
    sub_agents: List[str]
    dependencies: List[Dependency]
    output_schema: str  # JSON schema as a string
