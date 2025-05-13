import json
from constants import SYSTEM_PROMPT_BASE, SYSTEM_PROMPT_JOURNEY_INSTRUCTIONS

SEQUENCES = {
    "test-seq": {
        "id": "test-seq",
        "steps": [
            # Required: [type, id]
            {"type": "agent", "id": "detect_unsubscribe", "output_key": "unsubscribe_result",
             "arguments": {"incoming_message": {"type": "dynamic", "value": 'incoming_message["content"]'}}},
            {"type": "tool", "id": "detect_opt_out"},
            {"type": "tool", "id": "get_journey_instruction", "skip_conditions": {"detect_opt_out_result": True},
             "arguments": {"client_id": {"type": "static", "value": "bobola-dealership"}},
             "output_key": "journey_instructions"},
            {"type": "agent", "id": "reply_agent", "output_key": "reply",
             "skip_conditions": {"detect_opt_out_result": True},
             "arguments": {"incoming_message": {"type": "dynamic", "value": 'incoming_message["content"]'}}},
            {"type": "agent", "id": "assess_human_takeover", "skip_conditions": {"detect_opt_out_result": True}},
            {"type": "tool", "id": "append_signature"},
            {"type": "tool", "id": "send_reply"},
        ],
    }
}

AGENTS = {
    "detect_unsubscribe": {
        # Required: [id, name, model, prompt, tools, sub-agents, output-schema]
        "id": "detect_unsubscribe",
        "name": "UnsubscribeDetector",
        "model": "openai:gpt-4.1",
        "prompt": [
            (
                'system',
                ("Given the customer’s latest message, detect if they want to unsubscribe. "
                 "If yes, set unsubscribe to True and reply to 'Your unsubscribe has been processed.' "
                 "Else, set unsubscribe to False and set reply to an empty string.")
            ),
            (
                'user',
                '{incoming_message}'
            )
        ],
        "tools": [],
        "sub-agents": [],
        "dependencies": [{"key": "incoming_message", "default_value": None, "override": False}],
        "output-schema": json.dumps({
            "type": "object",
            "properties": {
                "unsubscribe": {"type": "boolean"},
                "reply": {"type": "string"}
            },
            "required": ["unsubscribe", "reply"]
        })
    },
    "reply_agent": {
        "id": "reply_agent",
        "name": "StructuredReplyAgent",
        "model": "openai:gpt-4.1",
        "prompt": [
            (
                'system',
                SYSTEM_PROMPT_BASE + SYSTEM_PROMPT_JOURNEY_INSTRUCTIONS,
            ),
            (
                'user',
                '{incoming_message}'
            )
        ],
        "tools": ["get_conversation_history", "get_appointment_hours", "get_inventory_information",
                  "schedule_appointment", "get_current_time", ],
        "sub-agents": [],
        "dependencies": [
            {"key": "preferred_tone", "default_value": "polite", "override": True},
            {"key": "journey_instruction", "default_value": None, "override": False},
            {"key": "incoming_message", "default_value": None, "override": False}
        ],
        "output-schema": json.dumps({
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "content": {
                    "type": "object",
                    "properties": {
                        "greeting": {"type": "string"},
                        "body": {"type": "string"}
                    },
                    "required": ["greeting", "body"]
                },
                "missing_information": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["channel", "content", "missing_information"]
        })
    },
    "assess_human_takeover": {
        "id": "assess_human_takeover",
        "name": "HumanTakeoverAssessor",
        "model": "openai:gpt-4.1",
        "prompt": [
            (
                'system',
                ("Given the list of missing information, decide if human takeover is needed meaning that there's a "
                 "significant lack of information and conversation quality would benefit from a dealership "
                 "representative who can reply and fill the gaps. "
                 "If yes, call the 'set_hto' tool and set 'hto_required' to True else set 'hto_required' to False.")
            ),
            (
                'user',
                'Missing information: {reply[missing_information]}'
            )
        ],
        "dependencies": [
            {"key": "reply[missing_information]", "default_value": None, "override": False},
        ],
        "sub-agents": [],
        "output-schema": json.dumps({
            "type": "object",
            "properties": {
                "hto_required": {"type": "boolean"}
            },
            "required": ["hto_required"]
        })
    }
}

CLIENT_CONFIGS = {
    "client-123": {
        # Generic key-value pairs
        "preferred_tone": "angelic",
    }
}
