import os
import time
import json
import logging

import requests
import threading
from requests import RequestException
from typing import Dict, Tuple, List, Optional

from distributed_state_network.objects.packets import BootstrapPacket, HelloPacket
from distributed_state_network.objects.state import NodeState
from distributed_state_network.objects.config import DSNodeConfig

from distributed_state_network.util import get_dict_hash
from distributed_state_network.util.cert import CertManager
from distributed_state_network.util.aes import aes_encrypt, aes_decrypt, generate_aes_key

TICK_INTERVAL = 3

class DSNode:
    config: DSNodeConfig
    node_states: Dict[str, NodeState]
    shutting_down: bool = False

    def __init__(
            self, 
            config: DSNodeConfig,
            version: str,
        ):
        self.config = config
        self.node_states = {
            self.config.node_id: NodeState(self.config.node_id, ("127.0.0.1", config.port), version, time.time(), { })
        }
        self.cert_manager = CertManager(config.node_id)
        CertManager.generate_certs(config.node_id)
        self.logger = logging.getLogger("DSN: " + config.node_id)
        if not os.path.exists(config.aes_key_file):
            raise Exception(f"Could not find aes key file in {config.aes_key_file}")
        threading.Thread(target=self.network_tick).start()

    def get_aes_key(self):
        with open(self.config.aes_key_file, 'rb') as f:
            return f.read()

    def network_tick(self):
        time.sleep(TICK_INTERVAL)
        if self.shutting_down:
            self.logger.info(f"Shutting down node")
            return
        self.test_connections()
        threading.Thread(target=self.network_tick).start()

    def test_connections(self):
        def remove(node_id: str):
            if node_id in self.node_states:
                del self.node_states[node_id]
                self.logger.info(f"PING failed for {node_id}, disconnecting...")
        for node_id in self.node_states.copy().keys():
            if not node_id in self.node_states or node_id == self.config.node_id:
                continue
            try:
                if self.shutting_down:
                    return
                self.send_ping(node_id)
            except RequestException:
                if node_id in self.node_states: # double check if something has changed since the ping request started
                    remove(node_id)

    def send_request_to_node(self, node_id: str, path: str, payload: bytes, verify) -> Tuple[requests.Response, bytes]:
        ip, port = self.connection_from_node(node_id)
        return self.send_request((ip, port), path, payload, verify)

    def send_request(self, con: Tuple[str, int], path: str, payload: bytes, verify, retries: int = 0) -> Tuple[requests.Response, bytes]:
        res = None
        try:
            res = requests.post(f'https://{con[0]}:{con[1]}/{path}', data=self.encrypt_data(payload), verify=verify, timeout=2)
        except Exception as e:
            self.logger.error(e)
            time.sleep(1)
            if retries < 2:
                self.send_request(con, path, payload, verify, retries + 1)
            else:
                raise RequestException(f'!!ERROR!! {path.upper()} => {con[0]}:{con[1]} (no response)')
        if res.status_code != 200:
            raise RequestException(f'!!ERROR!! {path.upper()} => {con[0]}:{con[1]} (status code {res.status_code})')
        
        possible_responses = [
            b'DOWN',
            b'Not Authorized',
            b'Bad Request Data'
        ]

        if res.content in possible_responses:
            raise RequestException(f'!!ERROR!! {path.upper()} => {con[0]}:{con[1]} ({res.content})')
        
        decrypted_data = b''
        if len(res.content) > 0:
            try:
                decrypted_data = self.decrypt_data(res.content)
            except Exception as e:
                raise RequestException(f'!!ERROR!! {path.upper()} => {con[0]}:{con[1]} (cannot decrypt response)')

        return res, decrypted_data

    def encrypt_data(self, data: bytes) -> bytes:
        return aes_encrypt(self.get_aes_key(), data)

    def decrypt_data(self, data: bytes) -> bytes:
        return aes_decrypt(self.get_aes_key(), data)

    def send_hello(self, node_id: str):
        self.logger.info(f"HELLO => {node_id}")

        payload = HelloPacket(self.config.node_id, self.cert_manager.my_cert()).to_bytes()
        
        try:
            res, content = self.send_request_to_node(node_id, 'hello', payload, False)
        except Exception as e:
            raise RequestException(f"!!ERROR!! HELLO => {node_id} ({e})")

        self.cert_manager.ensure_cert(node_id, content)

    def handle_hello(self, data: bytes) -> bytes:
        try:
            pkt = HelloPacket.from_bytes(data)
        except Exception as e:
            self.logger.error(e)
            return b'Bad Request Data'
        
        self.cert_manager.ensure_cert(pkt.node_id, pkt.https_certificate)

        return self.cert_manager.my_cert()

    def send_ping(self, node_id: str):     
        try:
            self.send_request_to_node(node_id, 'ping', b' ', verify=self.cert_manager.cert_path(node_id))
        except Exception as e:
            raise RequestException(f'!!ERROR!! PING => {node_id}: {e}')

    def send_bootstrap(self, con: Tuple[str, int]) -> str:
        cert_bytes = self.cert_manager.read_cert(self.config.node_id)
        state = { self.config.node_id: self.my_state() }
        payload = BootstrapPacket(self.my_version(), self.config.node_id, cert_bytes, state).to_bytes()
        name = f'{con[0]}:{con[1]}'
        self.logger.info(f"BOOTSTRAP => {name}")
        
        try:
            res, content = self.send_request(con, 'bootstrap', payload, False)
        except Exception as e:
            raise RequestException(f'!!ERROR!! BOOTSTRAP => {name} {e}')
       
        pkt = BootstrapPacket.from_bytes(content)
    
        self.node_states = pkt.state_data
        self.cert_manager.ensure_cert(pkt.node_id, pkt.https_certificate)

        return pkt.node_id

    def handle_bootstrap(self, data: bytes) -> bytes:
        try:
            pkt = BootstrapPacket.from_bytes(data)
        except Exception as e:
            self.logger.error(f'Bad packet: {e}')
            return b'Bad Packet'

        if pkt.version != self.my_version():
            msg = f"!!ERROR!! BOOTSTRAP => {state.node_id} (Version mismatch {state.version} != {self.my_version()})"
            self.logger.error(msg)
            return f'Version mismatch {state.version} != {self.my_version()}'.encode('utf-8')

        self.cert_manager.ensure_cert(pkt.node_id, pkt.https_certificate)
        self.node_states[pkt.node_id] = pkt.state_data[pkt.node_id]

        my_cert = self.cert_manager.read_cert(self.config.node_id)
        return BootstrapPacket(self.my_version(), self.config.node_id, my_cert, self.node_states).to_bytes()

    def send_update(self, node_id: str):
        try:
            self.logger.info(f"UPDATE => {node_id}")
            self.send_request_to_node(node_id, 'update', self.my_state().to_bytes(), self.cert_manager.cert_path(node_id))
        except Exception as e:
            self.logger.error(f"!!ERROR!! UPDATE => {node_id}: {e}")

    def handle_update(self, data: bytes):
        pkt = NodeState.from_bytes(data)
        
        if pkt.node_id == self.config.node_id:
            return # ignore if we accidentally sent an update to ourselves
        
        if pkt.node_id in self.node_states and self.node_states[pkt.node_id].last_update > pkt.last_update:
            return # don't use packets older than last update
        
        if not pkt.node_id in self.node_states:
            self.node_states[pkt.node_id] = pkt
            return

        if get_dict_hash(self.node_states[pkt.node_id].state_data) != get_dict_hash(pkt.state_data):
            self.node_states[pkt.node_id] = pkt

    def my_version(self):
        return self.my_state().version

    def my_state(self):
        return self.node_states[self.config.node_id]

    def bootstrap(self, con: Tuple[str, int]) -> bool:
        bootstrap_id = self.send_bootstrap(con)
        for n in list(self.node_states.keys())[:]:
            if n != self.config.node_id and n != bootstrap_id:
                try:
                    self.send_hello(n)
                    self.send_update(n)
                except RequestException as e:
                    self.logger.error(e)
                    del self.node_states[n]
                
    def connection_from_node(self, node_id: str) -> Tuple[str, int]:
        if node_id not in self.node_states:
            raise Exception(f"could not find connection for {node_id}")
        state = self.node_states[node_id]
        return (state.ip, state.port)

    def update_data(self, key: str, val: str):
        self.node_states[self.config.node_id].update_state(key, val)
        for key in list(self.node_states.keys())[:]:
            if key == self.config.node_id:
                continue
            self.send_update(key)

    def my_con(self) -> Tuple[str, int]:
        return self.connection_from_node(self.config.node_id)

    def get_address(self, node_id: str) -> Tuple[str, int]:
        return self.connection_from_node(node_id)

    def my_port(self) -> int:
        return self.my_state().port

    def read_data(self, node_id: str, key: str) -> Optional[str]:
        if key not in self.node_states[node_id].state_data.keys():
            return None
        return self.node_states[node_id].state_data[key]

    def get_certificate(self, node_id: str) -> Optional[str]:
        path = self.cert_manager.cert_path(node_id)
        if not os.path.exists(path):
            return None
        return path

    def peers(self) -> List[str]:
        return list(self.node_states.keys())

    def public_key_file(self) -> Optional[str]:
        return self.get_certificate(self.config.node_id)

    def private_key_file(self) -> Optional[str]:
        cert = self.get_certificate(self.config.node_id)
        if cert is None:
            return None
        return cert.replace(".crt", ".key")