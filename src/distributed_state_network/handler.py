import ssl
import threading
import json
import logging
from typing import Tuple
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

from distributed_state_network.dsnode import DSNode
from distributed_state_network.objects.config import DSNodeConfig
from distributed_state_network.util.aes import generate_aes_key
from distributed_state_network.util import stop_thread

VERSION = "0.0.1"
logging.basicConfig(level=logging.INFO)

def respond_bytes(handler: BaseHTTPRequestHandler, data: bytes):
    handler.send_response(200)
    handler.send_header("Content-Type", "application/octet-stream")
    handler.end_headers()
    handler.wfile.write(data)
    handler.wfile.flush()

class DSNodeHandler(BaseHTTPRequestHandler):
    server: "NodeServer"

    def do_POST(self):
        if self.server.node.shutting_down:
            respond_bytes(self, b'DOWN')
        
        content_length = int(self.headers.get('Content-Length', 0))
        try:
            body = self.server.node.decrypt_data(self.rfile.read(content_length))
        except Exception as e:
            self.server.node.logger.error(f"{self.path}: Error decrypting data, {e}")
            respond_bytes(self, b'Not Authorized')
            return

        if self.path == "/bootstrap":
            res = self.server.node.handle_bootstrap(body)
            respond_bytes(self, self.server.node.encrypt_data(res))

        elif self.path == "/hello":
            res = self.server.node.handle_hello(body)
            respond_bytes(self, self.server.node.encrypt_data(res))

        elif self.path == "/update":
            Thread(target=self.server.node.handle_update, args=(body, )).start()
            respond_bytes(self, b'')

        elif self.path == "/ping":
            respond_bytes(self, b'')

    def log_message(self, format, *args):
        pass

def serve(httpd):
    httpd.serve_forever()

class DSNodeServer(HTTPServer):
    def __init__(
        self, 
        config: DSNodeConfig
    ):
        super().__init__(("127.0.0.1", config.port), DSNodeHandler)
        self.node = DSNode(config, VERSION)
        self.config = config
        self.node.logger.info(f'Started DSNode on port {config.port}')

    def stop(self):
        self.shutdown()
        self.node.shutting_down = True
        self.socket.close()
        stop_thread(self.thread)

    @staticmethod
    def generate_key(out_file_path: str):
        key = generate_aes_key()
        with open(out_file_path, 'wb') as f:
            f.write(key)

    @staticmethod 
    def start(config: DSNodeConfig) -> 'NodeServer':
        n = DSNodeServer(config)
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cert_path = n.node.cert_manager.cert_path(config.node_id)
        ssl_context.load_cert_chain(
            certfile=cert_path,
            keyfile=cert_path.replace(".crt", ".key")
        )
        n.socket = ssl_context.wrap_socket(n.socket, server_side=True)
        n.thread = threading.Thread(target=serve, args=(n, ))
        n.thread.start()

        if config.bootstrap_nodes is not None and len(config.bootstrap_nodes) > 0:
            for bs in config.bootstrap_nodes:
                try:
                    n.node.bootstrap(bs)
                    break # Throws exception if connection is not made
                except Exception as e:
                    print(e)

        return n