import os
import time
import socket
import logging
import threading
from typing import Dict, List, Optional, Callable

from distributed_state_network.objects.endpoint import Endpoint
from distributed_state_network.objects.hello_packet import HelloPacket
from distributed_state_network.objects.peers_packet import PeersPacket
from distributed_state_network.objects.state_packet import StatePacket
from distributed_state_network.objects.config import DSNodeConfig

from distributed_state_network.util import get_dict_hash
from distributed_state_network.util.key_manager import CredentialManager
from distributed_state_network.util.aes import aes_encrypt, aes_decrypt

TICK_INTERVAL = 3
UDP_TIMEOUT = 2  # seconds

# Message type constants (must match handler.py)
MSG_HELLO = 1
MSG_PEERS = 2
MSG_UPDATE = 3
MSG_PING = 4

class DSNode:
    config: DSNodeConfig
    address_book: Dict[str, Endpoint]
    node_states: Dict[str, StatePacket]
    shutting_down: bool = False

    def __init__(
            self, 
            config: DSNodeConfig,
            version: str,
            sock: Optional[socket.socket] = None,
            disconnect_callback: Optional[Callable] = None,
            update_callback: Optional[Callable] = None
        ):
        self.config = config
        self.version = version
        self.socket = sock  # Use the server's socket for sending
        
        self.cred_manager = CredentialManager(config.node_id)
        self.cred_manager.generate_keys()
        
        self.node_states = {
            self.config.node_id: StatePacket.create(self.config.node_id, time.time(), self.cred_manager.my_private(), { })
        }

        # Determine initial IP - use 127.0.0.1 for localhost, will be updated when connecting to remote nodes
        initial_ip = "127.0.0.1"
        self.address_book = {
            self.config.node_id: Endpoint(initial_ip, config.port)
        }
        
        self.logger = logging.getLogger("DSN: " + config.node_id)
        self.disconnect_cb = disconnect_callback
        self.update_cb = update_callback
        if not os.path.exists(config.aes_key_file):
            raise Exception(f"Could not find aes key file in {config.aes_key_file}")
        
        # Response tracking for request/response matching
        self.pending_responses = {}
        self.response_lock = threading.Lock()
        
        threading.Thread(target=self.network_tick, daemon=True).start()

    def set_socket(self, sock: socket.socket):
        """Set the socket to use for sending requests"""
        self.socket = sock

    def get_aes_key(self):
        with open(self.config.aes_key_file, 'rb') as f:
            return f.read()

    def network_tick(self):
        time.sleep(TICK_INTERVAL)
        if self.shutting_down:
            self.logger.info("Shutting down node")
            return
        self.test_connections()
        threading.Thread(target=self.network_tick, daemon=True).start()

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
            except Exception:
                if node_id in self.node_states:  # double check if something has changed since the ping request started
                    remove(node_id)
                    if self.disconnect_cb is not None:
                        self.disconnect_cb()

    def send_udp_request(self, endpoint: Endpoint, msg_type: int, payload: bytes, retries: int = 0) -> bytes:
        """Send UDP request and wait for response using the server's socket"""
        if self.socket is None:
            raise Exception("Socket not set. Cannot send UDP request.")
        
        try:
            # Prepend message type and response bit (0 for request) to payload
            data_with_type = bytes([msg_type, 0]) + payload
            encrypted_data = self.encrypt_data(data_with_type)
            
            # Create a unique ID for this request based on endpoint and msg type
            request_id = (endpoint.address, endpoint.port, msg_type)
            
            # Set up response tracking
            response_event = threading.Event()
            with self.response_lock:
                self.pending_responses[request_id] = {'event': response_event, 'data': None}
            
            # Send the packet using the server's socket
            self.socket.sendto(encrypted_data, (endpoint.address, endpoint.port))
            
            # Wait for response
            if response_event.wait(timeout=UDP_TIMEOUT):
                with self.response_lock:
                    response_data = self.pending_responses[request_id]['data']
                    del self.pending_responses[request_id]
                
                if response_data is None:
                    raise Exception("Response was None")
                
                return response_data
            else:
                # Timeout
                with self.response_lock:
                    if request_id in self.pending_responses:
                        del self.pending_responses[request_id]
                raise socket.timeout("Request timed out")
            
        except socket.timeout:
            if retries < 2:
                time.sleep(0.5)
                return self.send_udp_request(endpoint, msg_type, payload, retries + 1)
            else:
                raise Exception(f"UDP request to {endpoint.to_string()} timed out")
        except Exception as e:
            if retries < 2:
                time.sleep(0.5)
                return self.send_udp_request(endpoint, msg_type, payload, retries + 1)
            else:
                raise Exception(f"UDP request to {endpoint.to_string()} failed: {e}")

    def handle_response(self, data: bytes, addr: tuple):
        """Handle incoming response and match it to pending request"""
        try:
            # Decrypt the data
            decrypted = self.decrypt_data(data)
            
            if len(decrypted) < 2:
                return
            
            # First byte is message type, second byte is response bit
            msg_type = decrypted[0]
            is_response = decrypted[1]
            if not is_response:
                return
            body = decrypted[2:]
            
            # Find matching pending request
            request_id = (addr[0], addr[1], msg_type)
            
            with self.response_lock:
                if request_id in self.pending_responses:
                    self.pending_responses[request_id]['data'] = body
                    self.pending_responses[request_id]['event'].set()
        except Exception as e:
            self.logger.error(f"Error handling response from {addr}: {e}")

    def send_request_to_node(self, node_id: str, msg_type: int, payload: bytes) -> bytes:
        con = self.connection_from_node(node_id)
        return self.send_udp_request(con, msg_type, payload)

    def encrypt_data(self, data: bytes) -> bytes:
        return aes_encrypt(self.get_aes_key(), data)

    def decrypt_data(self, data: bytes) -> bytes:
        return aes_decrypt(self.get_aes_key(), data)

    def request_peers(self, node_id: str):
        pkt = PeersPacket(self.config.node_id, None, { })
        pkt.sign(self.cred_manager.my_private())
        content = self.send_request_to_node(node_id, MSG_PEERS, pkt.to_bytes())
        pkt = PeersPacket.from_bytes(content)
        if not pkt.verify_signature(self.cred_manager.read_public(node_id)):
            raise Exception("Could not verify peers packet")

        for key in pkt.connections.keys():
            if key == self.config.node_id:
                continue
            
            self.address_book[key] = pkt.connections[key]
            
            if key not in self.node_states:
                self.send_hello(self.address_book[key])
            
            node_state = self.send_update(key)
            self.handle_update(node_state)

    def handle_peers(self, data: bytes):
        pkt = PeersPacket.from_bytes(data)
        if pkt.node_id not in self.address_book:
            raise Exception(401, f"Could not find {pkt.node_id} in address book")  # Not Authorized
        
        if not pkt.verify_signature(self.cred_manager.read_public(pkt.node_id)):
            raise Exception(406, "Could not verify ECDSA signature of packet")  # Not Acceptable

        peers = { }
        for key in self.address_book.keys():
            peers[key] = self.address_book[key]
        
        pkt = PeersPacket(self.config.node_id, None, peers)
        pkt.sign(self.cred_manager.my_private())
        return pkt.to_bytes()

    def send_hello(self, con: Endpoint):
        self.logger.info(f"HELLO => {con.to_string()}")

        payload = self.my_hello_packet().to_bytes()
        content = self.send_udp_request(con, MSG_HELLO, payload)
        
        # Get the response packet
        pkt = HelloPacket.from_bytes(content)
        self.logger.info(f"Received HELLO from {pkt.node_id}")
        
        # Verify version compatibility
        if pkt.version != self.version:
            msg = f"HELLO => {pkt.node_id} (Version mismatch \"{pkt.version}\" != \"{self.version}\")"
            self.logger.error(msg)
            raise Exception(505)  # Version not supported

        # Store the peer's public key
        self.cred_manager.ensure_public(pkt.node_id, pkt.ecdsa_public_key)
        
        # If the server sent us our detected IP, update our address book
        if pkt.detected_address:
            self.logger.info(f"Server detected our IP as: {pkt.detected_address}")
            # Update our own connection in the address book with the detected IP
            self.address_book[self.config.node_id] = Endpoint(pkt.detected_address, self.config.port)
        
        # Store the peer's connection info
        if pkt.node_id not in self.address_book:
            self.address_book[pkt.node_id] = pkt.connection

        if pkt.node_id not in self.node_states:
            self.node_states[pkt.node_id] = StatePacket(pkt.node_id, 0, b'', { })

        return pkt.node_id

    def handle_hello(self, data: bytes, detected_address: str = None) -> bytes | None:
        pkt = HelloPacket.from_bytes(data)
        self.logger.info(f"Received HELLO from {pkt.node_id}")
        if pkt.version != self.version:
            msg = f"HELLO => {pkt.node_id} (Version mismatch \"{pkt.version}\" != \"{self.version}\")"
            self.logger.error(msg)
            raise Exception(505)  # Version not supported

        self.cred_manager.ensure_public(pkt.node_id, pkt.ecdsa_public_key)
        
        if pkt.node_id not in self.address_book:
            self.address_book[pkt.node_id] = pkt.connection
        else:
            return None

        if pkt.node_id not in self.node_states:
            self.node_states[pkt.node_id] = StatePacket(pkt.node_id, 0, b'', { })

        # Create response with detected address
        response_pkt = self.my_hello_packet()
        response_pkt.detected_address = detected_address
        return response_pkt.to_bytes()

    def my_hello_packet(self) -> HelloPacket:
        pkt = HelloPacket(
            self.version, 
            self.config.node_id, 
            self.my_con(), 
            self.cred_manager.my_public(), 
            None,
            None  # No certificate for UDP
        )
        pkt.sign(self.cred_manager.my_private())
        return pkt

    def send_ping(self, node_id: str):     
        try:
            self.send_request_to_node(node_id, MSG_PING, b' ')
        except Exception as e:
            raise Exception(f'PING => {node_id}: {e}')

    def send_update(self, node_id: str):
        self.logger.info(f"UPDATE => {node_id}")
        content = self.send_request_to_node(node_id, MSG_UPDATE, self.my_state().to_bytes())
        return content

    def handle_update(self, data: bytes):
        pkt = StatePacket.from_bytes(data)
        self.logger.info(f"Received UPDATE from {pkt.node_id}")
        
        # ignore if we accidentally sent an update to ourselves
        if pkt.node_id == self.config.node_id:
            raise Exception(406, "Origin and destination are the same")  # Not acceptable
        
        # don't use packets older than last update
        if pkt.node_id in self.node_states and self.node_states[pkt.node_id].last_update > pkt.last_update:
            raise Exception(406, "Update is stale")  # Not acceptable
        
        if not pkt.verify_signature(self.cred_manager.read_public(pkt.node_id)):
            raise Exception(401, "Could not verify ECDSA signature")  # Not authorized
        
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
        content = self.send_update(bootstrap_id)
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
