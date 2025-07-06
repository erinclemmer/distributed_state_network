import ssl
import threading
import json
import logging
from typing import Tuple, Callable, Dict
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

def respond_404(handler: BaseHTTPRequestHandler):
    handler.send_response(404)
    handler.end_headers()

def graceful_fail(httpd: BaseHTTPRequestHandler, body: bytes, fn: Callable):
    try:
        fn_result = fn(body)
        if fn_result is not None:
            respond_bytes(httpd, httpd.server.node.encrypt_data(fn_result))
        else:
            respond_bytes(httpd, b'')
    except Exception as e:
        httpd.server.node.logger.error(e)
        respond_bytes(httpd, str(e.args[0]).encode('utf-8'))

class DSNodeHandler(BaseHTTPRequestHandler):
    server: "NodeServer"

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        try:
            body = self.server.node.decrypt_data(self.rfile.read(content_length))
        except Exception as e:
            self.server.node.logger.error(f"{self.path}: Error decrypting data, {e}")
            respond_bytes(self, b'Not Authorized')
            return


        if self.path == "/hello":
            graceful_fail(self, body, self.server.node.handle_hello)
        
        elif self.path == "/peers":
            graceful_fail(self, body, self.server.node.handle_peers)

        elif self.path == "/update":
            graceful_fail(self, body, self.server.node.handle_update)

        elif self.path == "/ping":
            respond_bytes(self, b'')

        else:
            respond_404(self)

    def log_message(self, format, *args):
        pass

def serve(httpd):
    httpd.serve_forever()

class DSNodeServer(HTTPServer):
    def __init__(
        self, 
        config_dict: Dict
    ):
        super().__init__(("127.0.0.1", config_dict["port"]), DSNodeHandler)
        self.config = DSNodeConfig.from_dict(config_dict)
        self.node = DSNode(self.config, VERSION)
        self.node.logger.info(f'Started DSNode on port {self.config.port}')

    def stop(self):
        self.node.shutting_down = True
        self.shutdown()
        self.socket.close()
        stop_thread(self.thread)

    @staticmethod
    def generate_key(out_file_path: str):
        key = generate_aes_key()
        with open(out_file_path, 'wb') as f:
            f.write(key)

    @staticmethod 
    def start(config_dict: DSNodeConfig) -> 'NodeServer':
        n = DSNodeServer(config_dict)
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cert_path = n.node.cert_manager.cert_path(n.config.node_id)
        ssl_context.load_cert_chain(
            certfile=cert_path,
            keyfile=cert_path.replace(".crt", ".key")
        )
        n.socket = ssl_context.wrap_socket(n.socket, server_side=True)
        n.thread = threading.Thread(target=serve, args=(n, ))
        n.thread.start()

        if n.config.bootstrap_nodes is not None and len(n.config.bootstrap_nodes) > 0:
            for bs in n.config.bootstrap_nodes:
                try:
                    n.node.bootstrap(bs.to_json())
                    break # Throws exception if connection is not made
                except Exception as e:
                    print(e)

        return n