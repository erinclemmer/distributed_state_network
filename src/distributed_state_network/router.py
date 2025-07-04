import os
import time
import json
import logging

import requests
import threading
from requests import RequestException
from typing import Dict, Tuple, List, Optional

from distributed_state_network.objects.packets import BootstrapPacket, HelloPacket
from distributed_state_network.objects.state import RouterState
from distributed_state_network.objects.config import RouterConfig

from distributed_state_network.util import get_dict_hash
from distributed_state_network.util.cert import CertManager
from distributed_state_network.util.aes import aes_encrypt, aes_decrypt, generate_aes_key

TICK_INTERVAL = 3

class Router:
    config: RouterConfig
    router_states: Dict[str, RouterState]
    shutting_down: bool = False

    def __init__(
            self, 
            config: RouterConfig,
            protocol_version: str,
        ):
        self.config = config
        self.router_states = { }
        self.cert_manager = CertManager(config.router_id)
        CertManager.generate_certs(config.router_id)
        self.logger = logging.getLogger("DSN: " + config.router_id)
        self.logger.setLevel(0)
        if not os.path.exists(config.aes_key_file):
            raise Exception(f"Could not find aes key file in {config.aes_key_file}")
        
        self.router_states[self.config.router_id] = RouterState(self.config.router_id, ("127.0.0.1", config.port), protocol_version, time.time(), { })
        threading.Thread(target=self.network_tick).start()
        self.logger.info(f"Started router on port {self.config.port}")

    def get_aes_key(self):
        with open(self.config.aes_key_file, 'rb') as f:
            return f.read()

    def network_tick(self):
        time.sleep(TICK_INTERVAL)
        if self.shutting_down:
            self.logger.info(f"Shutting down router")
            return
        self.test_connections()
        threading.Thread(target=self.network_tick).start()

    def test_connections(self):
        def remove(rtr_id: str):
            if rtr_id in self.router_states:
                del self.router_states[rtr_id]
                self.logger.info(f"PING failed for {rtr_id}, disconnecting...")
        for rtr_id in self.router_states.copy().keys():
            if not rtr_id in self.router_states or rtr_id == self.config.router_id:
                continue
            try:
                try:
                    self.send_ping(rtr_id)
                except RequestException:
                    if rtr_id in self.router_states: # double check if something has changed since the ping request started
                        remove(rtr_id)
            except ValueError:
                pass

    def send_request_to_router(self, router_id: str, path: str, payload: bytes, verify) -> Tuple[requests.Response, bytes]:
        if router_id not in self.router_states:
            raise Exception(f"cannot send {path} to unknown router id: {router_id}")
        ip, port = self.connection_from_router(router_id)
        return self.send_request((ip, port), path, payload, verify)

    def send_request(self, con: Tuple[str, int], path: str, payload: bytes, verify, retries: int = 0) -> Tuple[requests.Response, bytes]:
        res = None
        try:
            res = requests.post(f'https://{con[0]}:{con[1]}/{path}', data=self.encrypt_data(payload), verify=verify, timeout=2)
            if not res:
                raise Exception("No response from server")
        except Exception as e:
            self.logger.error(e)
            time.sleep(1)
            if retries < 2:
                self.send_request(con, path, payload, verify, retries + 1)
            else:
                raise RequestException(f'!!ERROR!! {path.upper()} => {con[0]}:{con[1]} (no response)')
        if not res:
            raise RequestException(f'!!ERROR!! {path.upper()} => {con[0]}:{con[1]} (no response)')
        if res.status_code != 200:
            raise RequestException(f'!!ERROR!! {path.upper()} => {con[0]}:{con[1]} (status code {res.status_code})')
        
        if res.content == b'DOWN':
            raise RequestException(f'!!ERROR!! {path.upper()} => {con[0]}:{con[1]} (router is down)')

        if res.content == b'Not Authorized':
            raise RequestException(f'!!ERROR!! {path.upper()} => {con[0]}:{con[1]} (not authorized)')
        
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

    def send_hello(self, router_id: str):
        self.logger.info(f"HELLO => {router_id}")

        payload = HelloPacket(self.config.router_id, self.cert_manager.my_cert()).to_bytes()
        
        try:
            res, content = self.send_request_to_router(router_id, 'hello', payload, False)
        except Exception as e:
            raise RequestException(f"!!ERROR!! HELLO => {router_id} ({e})")

        self.cert_manager.ensure_cert(router_id, content)

    def handle_hello(self, data: bytes) -> bytes:
        try:
            pkt = HelloPacket.from_bytes(data)
        except Exception as e:
            self.logger.error(e)
            return b'Not Authorized'
        
        self.cert_manager.ensure_cert(pkt.router_id, pkt.https_certificate)

        return self.cert_manager.my_cert()

    def send_ping(self, router_id: str):
        if router_id not in self.router_states:
            raise Exception(f"cannot send PING to unknown router id: {router_id}")
        
        try:
            self.send_request_to_router(router_id, 'ping', b' ', verify=self.cert_manager.cert_path(router_id))
        except Exception as e:
            raise RequestException(f'!!ERROR!! PING => {router_id}: {e}')

    def send_bootstrap(self, con: Tuple[str, int]) -> str:
        cert_bytes = self.cert_manager.read_cert(self.config.router_id)
        payload = BootstrapPacket(self.my_version(), self.config.router_id, cert_bytes,  self.my_state().to_dict()).to_bytes()
        name = f'{con[0]}:{con[1]}'
        self.logger.info(f"BOOTSTRAP => {name}")
        
        try:
            res, content = self.send_request(con, 'bootstrap', payload, False)
        except Exception as e:
            raise RequestException(f'!!ERROR!! BOOTSTRAP => {name} {e}')
       
        pkt = BootstrapPacket.from_bytes(content)
    
        self.cert_manager.ensure_cert(pkt.router_id, pkt.https_certificate)

        for key in pkt.state_data.keys():
            if key != self.config.router_id:
                self.router_states[key] = RouterState.from_dict(pkt.state_data[key])

        return pkt.router_id

    def handle_bootstrap(self, data: bytes) -> bytes:
        try:
            pkt = BootstrapPacket.from_bytes(data)
        except Exception as e:
            self.logger.error(f'Bad packet: {e}')
            return b'Bad Packet'

        if pkt.version != self.my_version():
            msg = f"!!ERROR!! BOOTSTRAP => {state.router_id} (Version mismatch {state.version} != {self.my_version()})"
            self.logger.error(msg)
            return f'Version mismatch {state.version} != {self.my_version()}'.encode('utf-8')

        self.cert_manager.ensure_cert(pkt.router_id, pkt.https_certificate)
        self.router_states[pkt.router_id] = RouterState.from_dict(pkt.state_data)

        state_data = { }
        for key in self.router_states.keys():
            state_data[key] = self.router_states[key].to_dict()
        
        my_cert = self.cert_manager.read_cert(self.config.router_id)
        return BootstrapPacket(self.my_version(), self.config.router_id, my_cert, state_data).to_bytes()

    def send_update(self, router_id: str):
        try:
            self.logger.info(f"UPDATE => {router_id}")
            payload = json.dumps(self.my_state().to_dict()).encode('utf-8')
            self.send_request_to_router(router_id, 'update', payload, self.cert_manager.cert_path(router_id))
        except Exception as e:
            self.logger.error(f"!!ERROR!! UPDATE => {router_id}: {e}")

    def handle_update(self, data: bytes):
        pkt = RouterState.from_dict(json.loads(data.decode('utf-8')))
        if pkt.router_id == self.config.router_id:
            return
        if pkt.router_id in self.router_states and self.router_states[pkt.router_id].last_update > pkt.last_update:
            return # don't use packets older than last update
        
        if not pkt.router_id in self.router_states:
            self.router_states[pkt.router_id] = pkt
            return

        current_data = self.router_states[pkt.router_id]
        if get_dict_hash(current_data.to_dict()) != get_dict_hash(pkt.to_dict()):
            self.router_states[pkt.router_id] = pkt

    def my_version(self):
        return self.my_state().version

    def my_state(self):
        return self.router_states[self.config.router_id]

    def bootstrap(self, con: Tuple[str, int]) -> bool:
        bootstrap_id = self.send_bootstrap(con)
        for rtr in list(self.router_states.keys())[:]:
            if rtr != self.config.router_id and rtr != bootstrap_id:
                try:
                    self.send_hello(rtr)
                    self.send_update(rtr)
                except RequestException as e:
                    self.logger.error(e)
                    del self.router_states[rtr]
                
    def connection_from_router(self, router_id: str) -> Tuple[str, int]:
        if router_id not in self.router_states:
            raise Exception(f"could not find connection for {router_id}")
        state = self.router_states[router_id]
        return (state.ip, state.port)

    def update_data(self, key: str, val: str):
        self.router_states[self.config.router_id].update_state(key, val)
        for key in list(self.router_states.keys())[:]:
            if key == self.config.router_id:
                continue
            self.send_update(key)

    def my_con(self) -> Tuple[str, int]:
        return self.connection_from_router(self.config.router_id)

    def get_address(self, router_id: str) -> Tuple[str, int]:
        return self.connection_from_router(router_id)

    def my_port(self) -> int:
        return self.my_state().port

    def read_data(self, router_id: str, key: str) -> Optional[str]:
        if key not in self.router_states[router_id].state.keys():
            return None
        return self.router_states[router_id].state[key]

    def get_certificate(self, router_id: str) -> Optional[str]:
        path = self.cert_manager.cert_path(router_id)
        if not os.path.exists(path):
            return None
        return path

    def peers(self) -> List[str]:
        return list(self.router_states.keys())

    def public_key_file(self) -> Optional[str]:
        return self.get_certificate(self.config.router_id)

    def private_key_file(self) -> Optional[str]:
        cert = self.get_certificate(self.config.router_id)
        if cert is None:
            return None
        return cert.replace(".crt", ".key")