import os
import time
import logging

import requests
import threading
from requests import RequestException
from typing import Dict, Tuple, List, Optional, Callable

from distributed_state_network.objects.endpoint import Endpoint
from distributed_state_network.objects.hello_packet import HelloPacket
from distributed_state_network.objects.peers_packet import PeersPacket
from distributed_state_network.objects.state_packet import StatePacket
from distributed_state_network.objects.config import DSNodeConfig

from distributed_state_network.util import get_dict_hash
from distributed_state_network.util.key_manager import CertManager, CredentialManager
from distributed_state_network.util.aes import aes_encrypt, aes_decrypt

TICK_INTERVAL = 3

class DSNode:
    config: DSNodeConfig
    address_book: Dict[str, Endpoint]
    node_states: Dict[str, StatePacket]
    shutting_down: bool = False

    def __init__(
            self, 
            config: DSNodeConfig,
            version: str,
            disconnect_callback: Optional[Callable] = None,
            update_callback: Optional[Callable] = None
        ):
        self.config = config
        self.version = version
        
        self.cert_manager = CertManager(config.node_id)
        self.cred_manager = CredentialManager(config.node_id)

        if self.config.https:
            self.cert_manager.generate_keys(self.config.network_ip)
        self.cred_manager.generate_keys()
        
        self.node_states = {
            self.config.node_id: StatePacket.create(self.config.node_id, time.time(), self.cred_manager.my_private(), { })
        }

        self.address_book = {
            self.config.node_id: Endpoint(config.network_ip, config.port)
        }
        
        self.logger = logging.getLogger("DSN: " + config.node_id)
        self.disconnect_cb = disconnect_callback
        self.update_cb = update_callback
        if not os.path.exists(config.aes_key_file):
            raise Exception(f"Could not find aes key file in {config.aes_key_file}")
        threading.Thread(target=self.network_tick).start()

    def get_aes_key(self):
        with open(self.config.aes_key_file, 'rb') as f:
            return f.read()

    def network_tick(self):
        time.sleep(TICK_INTERVAL)
        if self.shutting_down:
            self.logger.info("Shutting down node")
            return
        self.test_connections()
        threading.Thread(target=self.network_tick).start()

    def test_connections(self):
        def remove(node_id: str):
            if node_id in self.node_states:
                del self.node_states[node_id]
                del self.address_book[node_id]
                self.logger.info(f"PING failed for {node_id}, disconnecting...")
        for node_id in self.node_states.copy().keys():
            if node_id not in self.node_states or node_id == self.config.node_id:
                continue
            try:
                if self.shutting_down:
                    return
                self.send_ping(node_id)
            except RequestException:
                if node_id in self.node_states: # double check if something has changed since the ping request started
                    remove(node_id)
                    if self.disconnect_cb is not None:
                        self.disconnect_cb()

    def send_request_to_node(self, node_id: str, path: str, payload: bytes, verify) -> Tuple[requests.Response, bytes]:
        con = self.connection_from_node(node_id)
        return self.send_request(con, path, payload, verify)

    def send_request(self, con: Endpoint, path: str, payload: bytes, verify, retries: int = 0) -> Tuple[requests.Response, bytes]:
        try:
            # Always send a ping first to throw an error if https validation does not work
            protocol = "https" if self.config.https else "http"
            verify = verify if self.config.https else None
            requests.post(f'{protocol}://{con.to_string()}/ping', data=self.encrypt_data(payload), verify=verify, timeout=2)
            res = requests.post(f'{protocol}://{con.to_string()}/{path}', data=self.encrypt_data(payload), verify=verify, timeout=2)
        except Exception as e:
            self.logger.error(e)
            time.sleep(1)
            if retries < 2:
                return self.send_request(con, path, payload, verify, retries + 1)
            else:
                raise RequestException(f'{path.upper()} => {con.to_string()} (no response)')
        return self.parse_response(con, path, res)

    def parse_response(self, con: Endpoint, path: str, res: requests.Response) -> Tuple[requests.Response, bytes]:
        if res.status_code != 200:
            raise RequestException(f'{path.upper()} => {con.to_string()} (status code {res.status_code})')
        
        decrypted_data = b''
        if len(res.content) > 0:
            try:
                decrypted_data = self.decrypt_data(res.content)
            except Exception as e:
                raise RequestException(f'{path.upper()} => {con.to_string()} (cannot decrypt response)')

        return res, decrypted_data

    def encrypt_data(self, data: bytes) -> bytes:
        return aes_encrypt(self.get_aes_key(), data)

    def decrypt_data(self, data: bytes) -> bytes:
        return aes_decrypt(self.get_aes_key(), data)

    def request_peers(self, node_id: str):
        pkt = PeersPacket(self.config.node_id, None, { })
        pkt.sign(self.cred_manager.my_private())
        res, content = self.send_request_to_node(node_id, 'peers', pkt.to_bytes(), self.cert_manager.public_path(node_id))
        pkt = PeersPacket.from_bytes(content)
        if not pkt.verify_signature(self.cred_manager.read_public(node_id)):
            raise Exception("Could not verify peers packet")

        for key in pkt.connections.keys():
            if key == self.config.node_id:
                continue
            
            self.address_book[key] = pkt.connections[key]
            
            if key not in self.node_states:
                self.send_hello(self.address_book[key])
            
            _, node_state = self.send_update(key)
            self.handle_update(node_state)

    def handle_peers(self, data: bytes):
        pkt = PeersPacket.from_bytes(data)
        if pkt.node_id not in self.address_book:
            raise Exception(401, f"Could not find {pkt.node_id} in address book") # Not Authorized
        
        if not pkt.verify_signature(self.cred_manager.read_public(pkt.node_id)):
            raise Exception(406, "Could not verify ECDSA signature of packet") # Not Acceptable

        peers = { }
        for key in self.address_book.keys():
            peers[key] = self.address_book[key]
        
        pkt = PeersPacket(self.config.node_id, None, peers)
        pkt.sign(self.cred_manager.my_private())
        return pkt.to_bytes()

    def send_hello(self, con: Endpoint):
        self.logger.info(f"HELLO => {con.to_string()}")

        payload = self.my_hello_packet().to_bytes()
        _, content = self.send_request(con, 'hello', payload, False)
        self.handle_hello(content)

        pkt = HelloPacket.from_bytes(content)
        return pkt.node_id

    def handle_hello(self, data: bytes) -> bytes:
        pkt = HelloPacket.from_bytes(data)
        self.logger.info(f"Received HELLO from {pkt.node_id}")
        if pkt.version != self.version:
            msg = f"HELLO => {pkt.node_id} (Version mismatch \"{pkt.version}\" != \"{self.version}\")"
            self.logger.error(msg)
            raise Exception(505) # Version not supported

        if self.config.https:
            self.cert_manager.ensure_public(pkt.node_id, pkt.https_certificate)
        self.cred_manager.ensure_public(pkt.node_id, pkt.ecdsa_public_key)
        
        if pkt.node_id not in self.address_book:
            self.address_book[pkt.node_id] = pkt.connection

        if pkt.node_id not in self.node_states:
            self.node_states[pkt.node_id] = StatePacket(pkt.node_id, 0, b'', { })

        return self.my_hello_packet().to_bytes()

    def my_hello_packet(self) -> HelloPacket:
        pkt = HelloPacket(
            self.version, 
            self.config.node_id, 
            self.my_con(), 
            self.cred_manager.my_public(), 
            None,
            self.cert_manager.my_public() if self.config.https else None
        )
        pkt.sign(self.cred_manager.my_private())
        return pkt

    def send_ping(self, node_id: str):     
        try:
            self.send_request_to_node(node_id, 'ping', b' ', verify=self.cert_manager.public_path(node_id))
        except Exception as e:
            raise RequestException(f'PING => {node_id}: {e}')

    def send_update(self, node_id: str):
        self.logger.info(f"UPDATE => {node_id}")
        return self.send_request_to_node(node_id, 'update', self.my_state().to_bytes(), self.cert_manager.public_path(node_id))

    def handle_update(self, data: bytes):
        pkt = StatePacket.from_bytes(data)
        self.logger.info(f"Received UPDATE from {pkt.node_id}")
        
        # ignore if we accidentally sent an update to ourselves
        if pkt.node_id == self.config.node_id:
            raise Exception(406, "Origin and destination are the same") # Not acceptable
        
        # don't use packets older than last update
        if pkt.node_id in self.node_states and self.node_states[pkt.node_id].last_update > pkt.last_update:
            raise Exception(406, "Update is stale") # Not acceptable
        
        if not pkt.verify_signature(self.cred_manager.read_public(pkt.node_id)):
            raise Exception(401, "Could not verify ECDSA signature") # Not authorized
        
        if pkt.node_id not in self.node_states:
            self.node_states[pkt.node_id] = pkt
            return

        if get_dict_hash(self.node_states[pkt.node_id].state_data) != get_dict_hash(pkt.state_data):
            self.node_states[pkt.node_id] = pkt

        if self.update_cb is not None:
            try:
                self.update_cb()
            except Exception as e:
                self.logger.error("Update Error Captured:")
                self.logger.error(str(e))

        return self.my_state().to_bytes()

    def my_state(self):
        return self.node_states[self.config.node_id]

    def bootstrap(self, con: Endpoint):
        bootstrap_id = self.send_hello(con)
        self.address_book[bootstrap_id] = con
        _, content = self.send_update(bootstrap_id)
        self.handle_update(content)
        self.request_peers(bootstrap_id)

    def connection_from_node(self, node_id: str) -> Endpoint:
        if node_id not in self.address_book:
            raise Exception(f"could not find connection for {node_id}")
        return self.address_book[node_id]

    def update_data(self, key: str, val: str):
        self.node_states[self.config.node_id].update_state(key, val, self.cred_manager.my_private())
        for key in list(self.node_states.keys())[:]:
            if key == self.config.node_id:
                continue
            try:
                self.send_update(key)
            except Exception as e:
                print(e)

    def my_con(self) -> Endpoint:
        return self.connection_from_node(self.config.node_id)

    def read_data(self, node_id: str, key: str) -> Optional[str]:
        if key not in self.node_states[node_id].state_data.keys():
            return None
        return self.node_states[node_id].state_data[key]

    def peers(self) -> List[str]:
        return list(self.node_states.keys())
