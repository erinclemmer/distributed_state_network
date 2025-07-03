from typing import Dict, List
from dataclasses import dataclass

from distributed_state_network.endpoint import Endpoint

@dataclass(frozen=True)
class RouterConfig:
    router_id: str
    port: int
    aes_key_file: str
    bootstrap_nodes: List[Endpoint]

    @staticmethod
    def from_dict(data: Dict) -> 'RouterConfig':
        return RouterConfig(data["router_id"], data["port"], data["aes_key_file"], [Endpoint.from_json(e) for e in data["bootstrap_nodes"]])
