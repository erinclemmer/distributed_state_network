import json
from io import BytesIO
from typing import Dict

from distributed_state_network.util import bytes_to_int, int_to_bytes

class BootstrapPacket:
    version: str
    router_id: str
    https_certificate: bytes
    state_data: Dict[str, str]

    def __init__(
        self,
        version: str,
        router_id: str,
        https_certificate: bytes,
        state_data: Dict[str, str]
    ):
        self.version = version
        self.router_id = router_id
        self.https_certificate = https_certificate
        self.state_data = state_data

    def to_bytes(self):
        bts = BytesIO()

        version = self.version.encode('utf-8')
        bts.write(int_to_bytes(len(version)))
        bts.write(version)

        my_id = self.router_id.encode('utf-8')
        bts.write(int_to_bytes(len(my_id)))
        bts.write(my_id)
        
        bts.write(int_to_bytes(len(self.https_certificate)))
        bts.write(self.https_certificate)

        state_bytes = json.dumps(self.state_data).encode('utf-8')
        bts.write(int_to_bytes(len(state_bytes)))
        bts.write(state_bytes)
        
        return bts.getvalue()

    @staticmethod
    def from_bytes(data: bytes):
        bts = BytesIO(data)
        
        l = bytes_to_int(bts.read(4))
        version = bts.read(l).decode('utf-8')

        l = bytes_to_int(bts.read(4))
        router_id = bts.read(l).decode('utf-8')

        l = bytes_to_int(bts.read(4))
        https_certificate = bts.read(l)

        l = bytes_to_int(bts.read(4))
        state_data = json.loads(bts.read(l).decode('utf-8'))
        
        return BootstrapPacket(version, router_id, https_certificate, state_data)
        

class HelloPacket:
    router_id: str
    https_certificate: bytes

    def __init__(self, router_id: str, https_certificate: bytes):
        self.router_id = router_id
        self.https_certificate = https_certificate

    def to_bytes(self):
        bts = BytesIO()

        rtr_id = self.router_id.encode('utf-8')
        bts.write(int_to_bytes(len(rtr_id)))
        bts.write(rtr_id)

        bts.write(int_to_bytes(len(self.https_certificate)))
        bts.write(self.https_certificate)

        return bts.getvalue()

    @staticmethod
    def from_bytes(data: bytes):
        bts = BytesIO(data)

        l = bytes_to_int(bts.read(4))
        rtr_id = bts.read(l)

        l = bytes_to_int(bts.read(4))
        https_certificate = bts.read(l)

        return HelloPacket(rtr_id, https_certificate)