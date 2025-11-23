import socket
import threading
import logging
from typing import Callable, Optional
from distributed_state_network.dsnode import DSNode
from distributed_state_network.objects.config import DSNodeConfig
from distributed_state_network.util.aes import generate_aes_key
from distributed_state_network.util import stop_thread

VERSION = "0.2.0"
logging.basicConfig(level=logging.INFO)

# Message type constants
MSG_HELLO = 1
MSG_PEERS = 2
MSG_UPDATE = 3
MSG_PING = 4

class DSNodeServer:
    def __init__(
        self, 
        config: DSNodeConfig,
        sock: Optional[socket.socket] = None,
        disconnect_callback: Optional[Callable] = None,
        update_callback: Optional[Callable] = None
    ):
        self.config = config
        self.running = True
        
        # Use provided socket or create new one
        if sock is not None:
            self.socket = sock
        else:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.bind(("0.0.0.0", config.port))
        
        # Create DSNode with the socket
        self.node = DSNode(config, VERSION, self.socket, disconnect_callback, update_callback)
        self.node.logger.info(f'Started DSNode on UDP port {config.port}')

    def stop(self):
        self.node.shutting_down = True
        self.running = False
        try:
            self.socket.close()
        except:
            pass
        stop_thread(self.thread)

    def handle_packet(self, data: bytes, addr: tuple):
        """Handle incoming UDP packet - either a request or a response"""
        try:
            # Decrypt the data
            decrypted = self.node.decrypt_data(data)
            
            if len(decrypted) == 0:
                return
            
            # First byte is message type
            msg_type = decrypted[0]
            body = decrypted[1:]
            
            # Check if this is a response to a pending request
            request_id = (addr[0], addr[1], msg_type)
            with self.node.response_lock:
                is_response = request_id in self.node.pending_responses
            
            if is_response:
                # This is a response to our request - route to response handler
                self.node.handle_response(data, addr)
            else:
                # This is a new request - handle it
                response = None
                
                if msg_type == MSG_HELLO:
                    # Pass the detected IP address to handle_hello
                    response = self.node.handle_hello(body, addr[0])
                    
                elif msg_type == MSG_PEERS:
                    response = self.node.handle_peers(body)
                    
                elif msg_type == MSG_UPDATE:
                    response = self.node.handle_update(body)
                    
                elif msg_type == MSG_PING:
                    response = b''
                
                # Send response if handler returned data
                if response is not None:
                    # Prepend message type to response
                    response_with_type = bytes([msg_type]) + response
                    encrypted_response = self.node.encrypt_data(response_with_type)
                    self.socket.sendto(encrypted_response, addr)
                
        except Exception as e:
            if len(e.args) >= 2:
                self.node.logger.error(f"Error handling packet from {addr}: {e.args[0]} {e.args[1]}")
            else:
                self.node.logger.error(f"Error handling packet from {addr}: {e}")

    def serve_forever(self):
        """Main UDP server loop"""
        while self.running:
            try:
                # Receive UDP packet (max 65507 bytes for UDP)
                data, addr = self.socket.recvfrom(65507)
                # Handle packet in separate thread to avoid blocking
                threading.Thread(target=self.handle_packet, args=(data, addr), daemon=True).start()
            except OSError:
                # Socket was closed
                if not self.running:
                    break
            except Exception as e:
                self.node.logger.error(f"Error in server loop: {e}")
                if not self.running:
                    break

    @staticmethod
    def generate_key(out_file_path: str):
        key = generate_aes_key()
        with open(out_file_path, 'wb') as f:
            f.write(key)

    @staticmethod 
    def start(
        config: DSNodeConfig, 
        sock: Optional[socket.socket] = None,
        disconnect_callback: Optional[Callable] = None, 
        update_callback: Optional[Callable] = None
    ) -> 'DSNodeServer':
        n = DSNodeServer(config, sock, disconnect_callback, update_callback)
        n.thread = threading.Thread(target=n.serve_forever, daemon=True)
        n.thread.start()

        if n.config.bootstrap_nodes is not None and len(n.config.bootstrap_nodes) > 0:
            for bs in n.config.bootstrap_nodes:
                try:
                    n.node.bootstrap(bs)
                    break # Throws exception if connection is not made
                except Exception as e:
                    print(e)

        return n
