import json
from io import BytesIO
from typing import Dict

from distributed_state_network.objects.state import NodeState
from distributed_state_network.util.byte_helper import ByteHelper
from distributed_state_network.util import bytes_to_int, int_to_bytes

class BootstrapPacket:
    version: str
    node_id: str
    https_certificate: bytes
    state_data: Dict[str, NodeState]

    def __init__(
        self,
        version: str,
        node_id: str,
        https_certificate: bytes,
        state_data: Dict[str, NodeState]
    ):
        self.version = version
        self.node_id = node_id
        self.https_certificate = https_certificate
        self.state_data = state_data

    def to_bytes(self):
        bts = ByteHelper()
        bts.write_string(self.version)
        bts.write_string(self.node_id)
        bts.write_bytes(self.https_certificate)
        
        bts.write_int(len(self.state_data.keys()))
        for key in self.state_data.keys():
            bts.write_string(key)
            bts.write_bytes(self.state_data[key].to_bytes())

        return bts.get_bytes()

    @staticmethod
    def from_bytes(data: bytes):
        bts = ByteHelper(data)
        version = bts.read_string()
        node_id = bts.read_string()
        https_certificate = bts.read_bytes()
        state_data = { }
        num_keys = bts.read_int()
        for i in range(num_keys):
            key = bts.read_string()
            state_data[key] = NodeState.from_bytes(bts.read_bytes())
        
        if version == '' or node_id == '' or https_certificate == b'':
            raise Exception("Bad Request Data")

        return BootstrapPacket(version, node_id, https_certificate, state_data)
        

class HelloPacket:
    node_id: str
    https_certificate: bytes

    def __init__(self, node_id: str, https_certificate: bytes):
        self.node_id = node_id
        self.https_certificate = https_certificate

    def to_bytes(self):
        bts = ByteHelper()
        bts.write_string(self.node_id)
        bts.write_bytes(self.https_certificate)
        
        return bts.get_bytes()

    @staticmethod
    def from_bytes(data: bytes):
        bts = ByteHelper(data)
        node_id = bts.read_string()
        https_certificate = bts.read_bytes()

        if node_id == '' or https_certificate == b'':
            raise Exception("Bad Request Data")
        
        return HelloPacket(node_id, https_certificate)