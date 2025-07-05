from io import BytesIO
from distributed_state_network.util import bytes_to_int, int_to_bytes

class ByteHelper:
    def __init__(self, data: bytes = None):
        self.bts = BytesIO(data)

    def write_string(self, s: str):
        encoded = s.encode('utf-8')
        self.write_bytes(encoded)

    def write_bytes(self, b: bytes):
        self.bts.write(int_to_bytes(len(b)))
        self.bts.write(b)

    def read_string(self):
        return self.read_bytes().decode('utf-8')

    def read_bytes(self):
        l = bytes_to_int(self.bts.read(4))
        return self.bts.read(l)

    def get_bytes(self):
        return self.bts.getvalue()