import json
from io import BytesIO
from typing import Dict

from distributed_state_network.objects.state import NodeState
from distributed_state_network.util.byte_helper import ByteHelper
from distributed_state_network.util import bytes_to_int, int_to_bytes

class HelloPacket:
    version: str
    node_id: str
    https_certificate: bytes
    state: NodeState

    def __init__(self, version: str, node_id: str, https_certificate: bytes, state: NodeState):
        self.version = version
        self.node_id = node_id
        self.https_certificate = https_certificate
        self.state = state

    def to_bytes(self):
        bts = ByteHelper()
        bts.write_string(self.version)
        bts.write_string(self.node_id)
        bts.write_bytes(self.https_certificate)
        bts.write_bytes(self.state.to_bytes())
        
        return bts.get_bytes()

    @staticmethod
    def from_bytes(data: bytes):
        bts = ByteHelper(data)
        version = bts.read_string()
        node_id = bts.read_string()
        https_certificate = bts.read_bytes()

        if version == '' or node_id == '' or https_certificate == b'':
            raise Exception("Bad Request Data")
        
        state = NodeState.from_bytes(bts.read_bytes())

        return HelloPacket(version, node_id, https_certificate, state)