from typing import Dict, List
from dataclasses import dataclass

from distributed_state_network.objects.endpoint import Endpoint

@dataclass(frozen=True)
class DSNodeConfig:
    node_id: str
    port: int
    https: bool
    network_ip: str
    aes_key_file: str
    bootstrap_nodes: List[Endpoint]

    @staticmethod
    def from_dict(data: Dict) -> 'DSNodeConfig':
        return DSNodeConfig(
            data["node_id"], 
            data["port"], 
            data["https"],
            data["network_ip"],
            data["aes_key_file"], 
            [Endpoint.from_json(e) for e in data["bootstrap_nodes"]]
        )
