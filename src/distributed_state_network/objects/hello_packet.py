import json
from io import BytesIO
from typing import Dict

from distributed_state_network.objects.state import NodeState
from distributed_state_network.objects.endpoint import Endpoint

from distributed_state_network.util.ecdsa import verify_signature
from distributed_state_network.util.byte_helper import ByteHelper
from distributed_state_network.util import bytes_to_int, int_to_bytes

class HelloPacket:
    version: str
    node_id: str
    connection: Endpoint
    ecdsa_public_key: bytes
    https_certificate: bytes

    def __init__(
        self, 
        version: str, 
        node_id: str, 
        connection: Endpoint,
        ecdsa_public_key: bytes,
        https_certificate: bytes
    ):
        self.version = version
        self.node_id = node_id
        self.connection = connection
        self.ecdsa_public_key = ecdsa_public_key
        self.https_certificate = https_certificate

    def to_bytes(self):
        bts = ByteHelper()
        bts.write_string(self.version)
        bts.write_string(self.node_id)
        bts.write_bytes(self.connection.to_bytes())
        bts.write_bytes(self.ecdsa_public_key)
        bts.write_bytes(self.https_certificate)
        
        return bts.get_bytes()

    @staticmethod
    def from_bytes(data: bytes):
        bts = ByteHelper(data)
        version = bts.read_string()
        node_id = bts.read_string()
        connection = Endpoint.from_bytes(bts.read_bytes())
        ecdsa_public_key = bts.read_bytes()
        https_certificate = bts.read_bytes()

        if version == '' or node_id == '' or ecdsa_public_key == b'' or https_certificate == b'':
            raise Exception("Bad Request Data")

        return HelloPacket(version, node_id, connection, ecdsa_public_key, https_certificate)