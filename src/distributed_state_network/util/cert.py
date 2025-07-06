import os
import logging
from typing import Callable, Tuple

from distributed_state_network.util.ecdsa import generate_key_pair
from distributed_state_network.util.https import generate_cert

class KeyManager:
    def __init__(
        self, 
        node_id: str, 
        folder: str,
        public_extension: str,
        private_extension: str,
        generate_keys: Callable[[], Tuple[bytes, bytes]]
    ):
        self.node_id = node_id
        self.folder = folder
        self.public_extension = public_extension
        self.private_extension = private_extension
        self.generate_keys = generate_keys

    def write_cert(self, node_id: str, cert: bytes):
        if not os.path.exists(self.folder):
            os.mkdir(self.folder)
        if not os.path.exists(f'{self.folder}/{node_id}'):
            os.mkdir(f'{self.folder}/{node_id}')
        with open(f'{self.folder}/{self.node_id}/{node_id}.{self.public_extension}', 'wb') as f:
            f.write(cert)

    def read_cert(self, node_id: str) -> bytes:
        if not os.path.exists(f'{self.folder}/{self.node_id}/{node_id}.{self.public_extension}'):
            return None
        with open(f'{self.folder}/{self.node_id}/{node_id}.{self.public_extension}', 'rb') as f:
            return f.read()

    def has_cert(self, node_id: str) -> bool:
        return os.path.exists(f'{self.folder}/{self.node_id}/{node_id}.{self.public_extension}')

    def ensure_cert(self, node_id: str, cert: bytes):
        if self.has_cert(node_id):
            if not self.verify_cert(node_id, cert):
                raise Exception(401)
        else:
            self.write_cert(node_id, cert)

    def cert_path(self, node_id: str):
        return f"{self.folder}/{self.node_id}/{node_id}.{self.public_extension}"

    def verify_cert(self, node_id: str, cert: bytes):
        if not self.has_cert(node_id):
            return False
        return cert == self.read_cert(node_id)

    def my_cert(self) -> bytes:
        return self.read_cert(self.node_id)

    def my_private(self):
        if not os.path.exists(f'{self.folder}/{self.node_id}/{self.node_id}.{self.private_extension}'):
            return None
        with open(f'{self.folder}/{self.node_id}/{self.node_id}.{self.private_extension}', 'rb') as f:
            return f.read()

    def generate_certs(self):
        if os.path.exists(f'{self.folder}/{self.node_id}/{self.node_id}.{self.private_extension}'):
            return
        logging.getLogger("DSN: " + self.node_id).info("Generating Keys ...")
        cert_bytes, key_bytes = self.generate_keys()
        if not os.path.exists(self.folder):
            os.mkdir(self.folder)
        if not os.path.exists(f'{self.folder}/{self.node_id}'):
            os.mkdir(f'{self.folder}/{self.node_id}')
        with open(f'{self.folder}/{self.node_id}/{self.node_id}.{self.public_extension}', 'wb') as f:
            f.write(cert_bytes)
        with open(f'{self.folder}/{self.node_id}/{self.node_id}.{self.private_extension}', 'wb') as f:
            f.write(key_bytes)

class CertManager(KeyManager):
    def __init__(self, node_id: str):
        KeyManager.__init__(self, node_id, "certs", "crt", "key", generate_cert)

class CredentialManager(KeyManager):
    def __init__(self, node_id: str):
        KeyManager.__init__(self, node_id, "credentials", "pub", "key", generate_key_pair)