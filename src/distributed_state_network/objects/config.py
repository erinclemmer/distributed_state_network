from typing import Dict, List
from dataclasses import dataclass

from distributed_state_network.objects.endpoint import Endpoint

@dataclass(frozen=True)
class DSNodeConfig:
    node_id: str
    port: int
    aes_key_file: str
    bootstrap_nodes: List[Endpoint]
    network_ip: str = "127.0.0.1"

    @staticmethod
    def from_dict(data: Dict) -> 'DSNodeConfig':
        return DSNodeConfig(
            data["node_id"], 
            data["port"], 
            data["aes_key_file"], 
            [Endpoint.from_json(e) for e in data["bootstrap_nodes"]],
            data.get("network_ip", "127.0.0.1")
        )
