import os
import logging

from distributed_state_network.util.https import generate_cert

class CertManager:
    def __init__(self, node_id: str):
        self.node_id = node_id

    def write_cert(self, node_id: str, cert: bytes):
        if not os.path.exists('certs'):
            os.mkdir('certs')
        if not os.path.exists(f'certs/{node_id}'):
            os.mkdir(f'certs/{node_id}')
        with open(f'certs/{self.node_id}/{node_id}.crt', 'wb') as f:
            f.write(cert)

    def read_cert(self, node_id: str) -> bytes:
        if not os.path.exists(f'certs/{self.node_id}/{node_id}.crt'):
            return None
        with open(f'certs/{self.node_id}/{node_id}.crt', 'rb') as f:
            return f.read()

    def has_cert(self, node_id: str) -> bool:
        return os.path.exists(f'certs/{self.node_id}/{node_id}.crt')

    def ensure_cert(self, node_id: str, cert: bytes):
        if self.has_cert(node_id):
            if not self.verify_cert(node_id, cert):
                raise Exception(f"[{self.node_id}] could not verify certificate from {node_id}")
        else:
            self.write_cert(node_id, cert)

    def cert_path(self, node_id: str):
        return f"certs/{self.node_id}/{node_id}.crt"

    def verify_cert(self, node_id: str, cert: bytes):
        if not self.has_cert(node_id):
            return False
        return cert == self.read_cert(node_id)

    def my_cert(self) -> bytes:
        return self.read_cert(self.node_id)

    @staticmethod
    def generate_certs(node_id: str):
        if os.path.exists(f'certs/{node_id}/{node_id}.key'):
            return
        logging.getLogger("LM NET: " + node_id).info("Generating self-signed certificate ...")
        cert_bytes, key_bytes = generate_cert()
        if not os.path.exists('certs'):
            os.mkdir('certs')
        if not os.path.exists(f'certs/{node_id}'):
            os.mkdir(f'certs/{node_id}')
        with open(f'certs/{node_id}/{node_id}.crt', 'wb') as f:
            f.write(cert_bytes)
        with open(f'certs/{node_id}/{node_id}.key', 'wb') as f:
            f.write(key_bytes)