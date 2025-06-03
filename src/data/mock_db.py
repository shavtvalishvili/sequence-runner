import json
from typing import Any

from src.agent.types import Agent
from src.data.constants import SYSTEM_PROMPT_BASE, SYSTEM_PROMPT_JOURNEY_INSTRUCTIONS
from src.sequence.types import Sequence

SEQUENCES: dict[str, Sequence] = {
    "test-seq": {
        "id": "test-seq",
        "steps": [
            # Required: [type, id]
            {
                "type": "agent",
                "id": "detect_unsubscribe",
                "output_key": "unsubscribe_result",
                "arguments": {
                    "incoming_message": {
                        "type": "dynamic",
                        "value": "incoming_message[content]",
                    }
                },
            },
            {"type": "tool", "id": "demo-detect_opt_out"},
            {
                "type": "tool",
                "id": "demo-get_journey_instruction",
                "skip_conditions": {"demo-detect_opt_out_result": True},
                "arguments": {
                    "client_id": {"type": "static", "value": "bobola-dealership"}
                },
                "output_key": "journey_instructions",
            },
            {
                "type": "agent",
                "id": "reply_agent",
                "output_key": "reply",
                "skip_conditions": {"demo-detect_opt_out_result": True},
                "arguments": {
                    "incoming_message": {
                        "type": "dynamic",
                        "value": "incoming_message[content]",
                    }
                },
            },
            {
                "type": "agent",
                "id": "assess_human_takeover",
                "skip_conditions": {"demo-detect_opt_out_result": True},
            },
            {"type": "tool", "id": "demo-append_signature"},
            {
                "type": "tool",
                "id": "demo-send_reply",
                "arguments": {
                    "append_signature_result": {
                        "type": "static",
                        "value": "demo-append_signature_result",
                    }
                },
            },
        ],
    },
    "agent-as-tool-seq": {
        "id": "agent-as-tool-seq",
        "steps": [
            {
                "type": "agent",
                "id": "mock-customer",
                "arguments": {
                    "incoming_message": {
                        "type": "dynamic",
                        "value": "incoming_message[content]",
                    }
                },
            }
        ],
    },
}

AGENTS: dict[str, Agent] = {
    "detect_unsubscribe": {
        # Required: [id, name, model, prompt, tools, sub_agents, output_schema]
        "id": "detect_unsubscribe",
        "name": "UnsubscribeDetector",
        "model": "openai:gpt-4.1",
        "prompt": [
            (
                "system",
                (
                    "Given the customer’s latest message, detect if they want to unsubscribe. "
                    "If yes, set unsubscribe to True and reply to 'Your unsubscribe has been processed.' "
                    "Else, set unsubscribe to False and set reply to an empty string."
                ),
            ),
            ("user", "{incoming_message}"),
        ],
        "tools": [],
        "sub_agents": [],
        "dependencies": [
            {"key": "incoming_message", "default_value": None, "override": False}
        ],
        "output_schema": json.dumps(
            {
                "type": "object",
                "properties": {
                    "unsubscribe": {"type": "boolean"},
                    "reply": {"type": "string"},
                },
                "required": ["unsubscribe", "reply"],
            }
        ),
    },
    "reply_agent": {
        "id": "reply_agent",
        "name": "StructuredReplyAgent",
        "model": "openai:gpt-4.1",
        "prompt": [
            (
                "system",
                SYSTEM_PROMPT_BASE + SYSTEM_PROMPT_JOURNEY_INSTRUCTIONS,
            ),
            ("user", "{incoming_message}"),
        ],
        "tools": [
            "demo-get_conversation_history",
            "demo-get_appointment_hours",
            "demo-get_inventory_information",
            "demo-schedule_appointment",
            "demo-get_current_time",
        ],
        "sub_agents": [],
        "dependencies": [
            {"key": "preferred_tone", "default_value": "polite", "override": True},
            {"key": "journey_instruction", "default_value": None, "override": False},
            {"key": "incoming_message", "default_value": None, "override": False},
        ],
        "output_schema": json.dumps(
            {
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "content": {
                        "type": "object",
                        "properties": {
                            "greeting": {"type": "string"},
                            "body": {"type": "string"},
                        },
                        "required": ["greeting", "body"],
                    },
                    "missing_information": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["channel", "content", "missing_information"],
            }
        ),
    },
    "assess_human_takeover": {
        "id": "assess_human_takeover",
        "name": "HumanTakeoverAssessor",
        "model": "openai:gpt-4.1",
        "prompt": [
            (
                "system",
                (
                    "Given the list of missing information, decide if human takeover is needed meaning that there's a "
                    "significant lack of information and conversation quality would benefit from a dealership "
                    "representative who can reply and fill the gaps. "
                    "If yes, call the 'set_hto' tool and set 'hto_required' to True else set 'hto_required' to False."
                ),
            ),
            ("user", "Missing information: {reply[missing_information]}"),
        ],
        "dependencies": [
            {
                "key": "reply[missing_information]",
                "default_value": None,
                "override": False,
            },
        ],
        "tools": [],
        "sub_agents": [],
        "output_schema": json.dumps(
            {
                "type": "object",
                "properties": {"hto_required": {"type": "boolean"}},
                "required": ["hto_required"],
            }
        ),
    },
    "mock-customer": {
        "id": "mock-customer",
        "name": "CustomerMockerAgent",
        "model": "openai:gpt-4.1",
        "prompt": [
            (
                "system",
                "Use the detect-tone tool to detect the tone of the user message and generate a reply mocking them in a similar tone.",
            ),
            ("user", "{incoming_message}"),
        ],
        "tools": [],
        "sub_agents": ["detect-tone"],
        "dependencies": [
            {"key": "incoming_message", "default_value": None, "override": False}
        ],
        "output_schema": json.dumps(
            {
                "type": "object",
                "properties": {"reply": {"type": "string"}},
                "required": ["reply"],
            }
        ),
    },
    "detect-tone": {
        "id": "detect-tone",
        "name": "CustomerMockerAgent",
        "model": "openai:gpt-4.1",
        "prompt": [
            (
                "system",
                "Detect the tone of the user message and categorize it into one of these categories:\n"
                "- Polite\n"
                "- Angry\n"
                "- Happy\n"
                "- Neutral\n"
                "- Sarcastic\n"
                "- Annoyed\n"
                "- Disappointed\n"
                "- Excited\n"
                "- Confused\n"
                "- Bored\n"
                "- Frustrated\n"
                "- Curious\n",
            ),
            ("user", "{incoming_message}"),
        ],
        "tools": [],
        "sub_agents": [],
        "dependencies": [
            {"key": "incoming_message", "default_value": None, "override": False}
        ],
        "output_schema": json.dumps(
            {
                "type": "object",
                "properties": {"tone": {"type": "string"}},
                "required": ["tone"],
            }
        ),
    },
}

CLIENT_CONFIGS: dict[str, dict[str, Any]] = {
    "client-123": {
        # Generic key-value pairs
        "preferred_tone": "angelic",
    }
}
