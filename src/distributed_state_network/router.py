import os
import time
import json
import logging

import requests
import threading
from requests import RequestException
from typing import Dict, Tuple, List, Optional

from distributed_state_network.objects.bootstrap_pkt import BootstrapPacket
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
        if not os.path.exists(config.aes_key_file):
            raise Exception(f"Could not find aes key file in {config.aes_key_file}")
        
        self.router_states[self.config.router_id] = RouterState(self.config.router_id, ("127.0.0.1", config.port), protocol_version, time.time(), { })
        threading.Thread(target=self.network_tick).start()

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

    def send_request_to_router(self, router_id: str, path: str, payload: Dict, verify):
        if router_id not in self.router_states:
            raise Exception(f"cannot send {path} to unknown router id: {router_id}")
        ip, port = self.connection_from_router(router_id)
        return self.send_request((ip, port), path, payload, verify)

    def send_request(self, con: Tuple[str, int], path: str, payload: Dict, verify, retries: int = 0):
        res = None
        try:
            res = requests.post(f'https://{con[0]}:{con[1]}/{path}', json=payload, verify=verify, timeout=2)
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
        return res

    def encrypt_data(self, data: Dict) -> bytes:
        return aes_encrypt(self.get_aes_key(), json.dumps(data).encode('utf-8'))

    def decrypt_data(self, data: bytes) -> Dict:
        return json.loads(aes_decrypt(self.get_aes_key(), data).decode('utf-8'))

    def send_hello(self, router_id: str):
        self.logger.info(f"HELLO => {router_id}")

        payload = {
                "router_id": self.config.router_id,
                "https_certificate": self.cert_manager.read_cert(self.config.router_id).hex()
        }

        try:
            res = self.send_request_to_router(router_id, 'hello', { "data": self.encrypt_data(payload).hex() }, False)
        except Exception as e:
            raise RequestException(f"!!ERROR!! HELLO => {router_id} ({e})")

        try:
            data = aes_decrypt(self.get_aes_key(), res.content)
        except Exception as e:
            self.logger.error(e)
            return b'Not Authorized'

        self.cert_manager.ensure_cert(router_id, data)

    def handle_hello(self, encrypted_data: Dict) -> bytes:
        try:
            data = self.decrypt_data(bytes.fromhex(encrypted_data["data"]))
        except Exception as e:
            self.logger.error(e)
            return b'Not Authorized'
        if "router_id" not in data or "https_certificate" not in data:
            raise Exception(f"bad hello packet")

        self.cert_manager.ensure_cert(data["router_id"], bytes.fromhex(data["https_certificate"]))

        return aes_encrypt(self.get_aes_key(), self.cert_manager.read_cert(self.config.router_id))

    def send_ping(self, router_id: str):
        if router_id not in self.router_states:
            raise Exception(f"cannot send PING to unknown router id: {router_id}")
        
        try:
            self.send_request_to_router(router_id, 'ping', {}, verify=self.cert_manager.cert_path(router_id))
        except Exception as e:
            raise RequestException(f'!!ERROR!! PING => {router_id}: {e}')

    def send_bootstrap(self, con: Tuple[str, int]) -> str:
        payload = BootstrapPacket.create_payload(self.my_version(), self.my_state().to_dict(), self.cert_manager.read_cert(self.config.router_id))
        name = f'{con[0]}:{con[1]}'
        self.logger.info(f"BOOTSTRAP => {name}")
        
        try:
            res = self.send_request(con, 'bootstrap', { "data": self.encrypt_data(payload).hex() }, False)
        except Exception as e:
            raise RequestException(f'!!ERROR!! BOOTSTRAP => {name} {e}')
       
        try:
            data = aes_decrypt(self.get_aes_key(), res.content)
        except Exception as e:
            msg = "Could not decrypt data from bootstrap"
            self.logger.exception(msg)
            raise Exception(msg)

        pkt = BootstrapPacket.from_bytes(data)
    
        self.cert_manager.ensure_cert(pkt.router_id, pkt.https_certificate)

        new_states = { }
        for key in pkt.state_data.keys():
            if key == self.config.router_id:
                new_states[self.config.router_id] = self.router_states[self.config.router_id]
            else:
                new_states[key] = RouterState.from_dict(pkt.state_data[key])

        self.router_states = new_states
        
        return pkt.router_id

    def handle_bootstrap(self, encrypted_data: Dict) -> bytes:
        try:
            data = self.decrypt_data(bytes.fromhex(encrypted_data["data"]))
        except Exception as e:
            self.logger.error(e)
            return b'Not Authorized'

        if "state" not in data or "https_certificate" not in data:
            raise Exception(f"bad bootstrap packet")

        state = RouterState.from_dict(data["state"])

        if state.version != self.my_version():
            msg = f"!!ERROR!! BOOTSTRAP => {state.router_id} (Version mismatch {state.version} != {self.my_version()})"
            self.logger.error(msg)
            return

        cert = bytes.fromhex(data["https_certificate"])
        self.cert_manager.ensure_cert(state.router_id, cert)
        self.router_states[state.router_id] = state

        cert = self.cert_manager.read_cert(self.config.router_id)
        state_data = { }
        for key in self.router_states.keys():
            state_data[key] = self.router_states[key].to_dict()
        
        pkt = BootstrapPacket(self.config.router_id, cert, state_data).to_bytes()
        return aes_encrypt(self.get_aes_key(), pkt)

    def send_update(self, router_id: str):
        try:
            self.logger.info(f"UPDATE => {router_id}")
            self.send_request_to_router(router_id, 'update', self.my_state().to_dict(), self.cert_manager.cert_path(router_id))
        except Exception as e:
            self.logger.error(f"!!ERROR!! UPDATE => {router_id}: {e}")

    def handle_update(self, data: Dict):
        pkt = RouterState.from_dict(data)
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
        for key in list(self.router_states.keys())[:]:
            if key != self.config.router_id and key != bootstrap_id:
                try:
                    self.send_hello(key)
                    self.send_update(key)
                except RequestException as e:
                    self.logger.error(e)
                    del self.router_states[key]
                
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