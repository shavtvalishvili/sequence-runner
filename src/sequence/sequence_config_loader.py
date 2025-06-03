from typing import Any

from src.agent.types import Agent
from src.data.mock_db import AGENTS, CLIENT_CONFIGS, SEQUENCES
from src.sequence.types import Sequence


class SequenceConfigLoader:
    def __init__(self) -> None:
        self._seqs = SEQUENCES
        self._clients = CLIENT_CONFIGS
        self._agents = AGENTS

    def load_sequence(self, sequence_id: str) -> Sequence:
        seq = self._seqs.get(sequence_id)
        if not seq:
            raise ValueError(f"Sequence {sequence_id} not found")
        return seq

    def load_client_config(self, client_id: str) -> dict[str, Any]:
        return self._clients.get(client_id, {})

    def load_all_agents(self) -> dict[str, Agent]:
        return self._agents.copy()
