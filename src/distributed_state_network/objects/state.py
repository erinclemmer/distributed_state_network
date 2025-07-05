import time
import json
from typing import Dict, Tuple

from distributed_state_network.objects.endpoint import Endpoint
from distributed_state_network.util.byte_helper import ByteHelper

class NodeState:
    node_id: str
    connection: Endpoint
    version: str
    state_data: Dict[str, str]
    last_update: float

    def __init__(
            self, 
            node_id: str, 
            connection: Endpoint,
            version: str,
            last_update: float,
            state_data: Dict[str, str],
        ):
        self.node_id = node_id
        self.connection = connection
        self.version = version
        self.state_data = state_data
        self.last_update = last_update

    def update_state(self, key: str, data: str):
        self.state_data[key] = data
        self.last_update = time.time()

    def to_bytes(self):
        bts = ByteHelper()
        bts.write_string(self.node_id)
        bts.write_string(self.connection.address)
        bts.write_int(self.connection.port)
        bts.write_string(self.version)
        bts.write_float(self.last_update)
        bts.write_string(json.dumps(self.state_data))

        return bts.get_bytes()
    
    @staticmethod
    def from_bytes(data: bytes):
        bts = ByteHelper(data)
        node_id = bts.read_string()
        ip = bts.read_string()
        port = bts.read_int()
        version = bts.read_string()
        
        if node_id == '' or ip == '' or version == '':
            raise Exception("Bad Request Data")
        
        last_update = bts.read_float()
        state_data = json.loads(bts.read_string())

        return NodeState(node_id, Endpoint(ip, port), version, last_update, state_data)