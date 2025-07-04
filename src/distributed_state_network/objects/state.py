import time
from typing import Dict, Tuple

class NodeState:
    node_id: str
    ip: str
    port: int
    version: str
    state: Dict[str, str]
    last_update: float

    def __init__(
            self, 
            node_id: str, 
            con: Tuple[str, int],
            version: str,
            last_update: float,
            state: Dict,
        ):
        self.node_id = node_id
        self.ip = con[0]
        self.port = con[1]
        self.version = version
        self.state = state
        self.last_update = last_update

    def update_state(self, key: str, data: str):
        self.state[key] = data
        self.last_update = time.time()
    
    def to_dict(self):
        return {
            "node_id": self.node_id,
            "ip": self.ip,
            "port": self.port,
            "version": self.version,
            "last_update": self.last_update,
            "state": self.state,
        }

    @staticmethod
    def from_dict(data):
        return NodeState(
            data["node_id"],
            (data["ip"], data["port"]),
            data["version"],
            data["last_update"],
            data["state"],
        )