import time
import json
from typing import Dict, Tuple

from distributed_state_network.util.ecdsa import verify_signature, sign_message
from distributed_state_network.objects.endpoint import Endpoint
from distributed_state_network.util.byte_helper import ByteHelper

class NodeState:
    node_id: str
    connection: Endpoint
    version: str
    ecdsa_signature: bytes
    state_data: Dict[str, str]
    last_update: float

    def __init__(
            self, 
            node_id: str, 
            connection: Endpoint,
            version: str,
            last_update: float,
            ecdsa_signature: bytes,
            state_data: Dict[str, str]
        ):
        self.node_id = node_id
        self.connection = connection
        self.version = version
        self.state_data = state_data
        self.last_update = last_update
        self.ecdsa_signature = ecdsa_signature

    def sign(self, private_key: bytes):
        self.ecdsa_signature = sign_message(private_key, self.to_bytes(False))

    def verify(self, public_key: bytes):
        return verify_signature(public_key, self.to_bytes(False), self.ecdsa_signature)

    def update_state(self, key: str, val: str, private_key: bytes):
        self.state_data[key] = val
        self.last_update = time.time()
        self.sign(private_key)

    def to_bytes(self, include_signature: bool = True):
        bts = ByteHelper()
        bts.write_string(self.node_id)
        bts.write_bytes(self.connection.to_bytes())
        bts.write_string(self.version)
        bts.write_float(self.last_update)
        if include_signature:
            bts.write_bytes(self.ecdsa_signature)
        bts.write_string(json.dumps(self.state_data))

        return bts.get_bytes()
    
    @staticmethod
    def create(
        node_id: str, 
        connection: Endpoint,
        version: str,
        last_update: float,
        ecdsa_private_key: bytes,
        state_data: Dict[str, str]
    ):
        s = NodeState(node_id, connection, version, last_update, b'', state_data)
        s.sign(ecdsa_private_key)
        return s


    @staticmethod
    def from_bytes(data: bytes):
        bts = ByteHelper(data)
        node_id = bts.read_string()
        connection = Endpoint.from_bytes(bts.read_bytes())
        version = bts.read_string()
        
        if node_id == '' or connection.address == '' or version == '':
            raise Exception(406) # Not acceptable
        
        last_update = bts.read_float()
        ecdsa_signature = bts.read_bytes()
        state_data = json.loads(bts.read_string())

        return NodeState(node_id, connection, version, last_update, ecdsa_signature, state_data)