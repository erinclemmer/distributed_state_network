import os
import logging

from distributed_state_network.util.https import generate_cert

class CertManager:
    def __init__(self, router_id: str):
        self.router_id = router_id

    def write_cert(self, router_id: str, cert: bytes):
        if not os.path.exists('certs'):
            os.mkdir('certs')
        if not os.path.exists(f'certs/{router_id}'):
            os.mkdir(f'certs/{router_id}')
        with open(f'certs/{self.router_id}/{router_id}.crt', 'wb') as f:
            f.write(cert)

    def read_cert(self, router_id: str) -> bytes:
        if not os.path.exists(f'certs/{self.router_id}/{router_id}.crt'):
            return b''
        with open(f'certs/{self.router_id}/{router_id}.crt', 'rb') as f:
            return f.read()

    def has_cert(self, router_id: str) -> bool:
        return os.path.exists(f'certs/{self.router_id}/{router_id}.crt')

    def ensure_cert(self, router_id: str, cert: bytes):
        if self.has_cert(router_id):
            if not self.verify_cert(router_id, cert):
                raise Exception(f"[{self.router_id}] could not verify certificate from {router_id}")
        else:
            self.write_cert(router_id, cert)

    def cert_path(self, router_id: str):
        return f"certs/{self.router_id}/{router_id}.crt"

    def verify_cert(self, router_id: str, cert: bytes):
        if not self.has_cert(router_id):
            return False
        return cert == self.read_cert(router_id)

    @staticmethod
    def generate_certs(router_id: str):
        if os.path.exists(f'certs/{router_id}/{router_id}.key'):
            return
        logging.getLogger("LM NET: " + router_id).info("Generating self-signed certificate ...")
        cert_bytes, key_bytes = generate_cert()
        if not os.path.exists('certs'):
            os.mkdir('certs')
        if not os.path.exists(f'certs/{router_id}'):
            os.mkdir(f'certs/{router_id}')
        with open(f'certs/{router_id}/{router_id}.crt', 'wb') as f:
            f.write(cert_bytes)
        with open(f'certs/{router_id}/{router_id}.key', 'wb') as f:
            f.write(key_bytes)