from mock_db import AGENTS, SEQUENCES, CLIENT_CONFIGS

class SequenceConfigLoader:
    def __init__(self):
        self._seqs = SEQUENCES
        self._clients = CLIENT_CONFIGS
        self._agents = AGENTS

    def load_sequence(self, sequence_id: str) -> dict:
        seq = self._seqs.get(sequence_id)
        if not seq:
            raise ValueError(f"Sequence {sequence_id} not found")
        return seq

    def load_client_config(self, client_id: str) -> dict:
        return self._clients.get(client_id, {})

    def load_all_agents(self) -> dict:
        return self._agents.copy()