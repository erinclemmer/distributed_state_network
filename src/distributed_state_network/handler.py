import ssl
import threading
import json
import logging
from typing import Tuple
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

from distributed_state_network.router import Router
from distributed_state_network.objects.config import RouterConfig
from distributed_state_network.util.aes import generate_aes_key
from distributed_state_network.util import stop_thread

VERSION = "0.0.1"
logging.basicConfig(level=logging.INFO)

def _send_403(handler: BaseHTTPRequestHandler, message: str):
    handler.send_response(403)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(message.encode())
    handler.wfile.flush()

def _respond_bytes(handler: BaseHTTPRequestHandler, data: bytes):
    handler.send_response(200)
    handler.send_header("Content-Type", "application/octet-stream")
    handler.end_headers()
    handler.wfile.write(data)
    handler.wfile.flush()

class RouterHandler(BaseHTTPRequestHandler):
    server: "RouterServer"

    def do_POST(self):
        if self.server.router.shutting_down:
            _respond_bytes(self, b'DOWN')
        
        content_length = int(self.headers.get('Content-Length', 0))
        try:
            body = self.server.router.decrypt_data(self.rfile.read(content_length))
        except Exception as e:
            self.server.router.logger.error(f"{self.path}: Error decrypting data, {e}")
            _respond_bytes(b'Not Authorized')
            return

        if self.path == "/bootstrap":
            res = self.server.router.handle_bootstrap(body)
            _respond_bytes(self, self.server.router.encrypt_data(res))

        elif self.path == "/hello":
            res = self.server.router.handle_hello(body)
            _respond_bytes(self, self.server.router.encrypt_data(res))

        elif self.path == "/update":
            Thread(target=self.server.router.handle_update, args=(body, )).start()
            _respond_bytes(self, b'')

        elif self.path == "/ping":
            _respond_bytes(self, b'')

    def log_message(self, format, *args):
        pass

def serve(httpd):
    httpd.serve_forever()

class RouterServer(HTTPServer):
    def __init__(
        self, 
        config: RouterConfig
    ):
        super().__init__(("127.0.0.1", config.port), RouterHandler)
        self.router = Router(config, VERSION)
        self.config = config
        self.router.logger.info(f'Started Router on port {config.port}')

    def stop(self):
        self.shutdown()
        self.router.shutting_down = True
        self.socket.close()
        stop_thread(self.thread)

    @staticmethod
    def generate_key(out_file_path: str):
        key = generate_aes_key()
        with open(out_file_path, 'wb') as f:
            f.write(key)

    @staticmethod 
    def start(config: RouterConfig) -> Tuple[Thread, 'RouterServer']:
        rtr = RouterServer(config)
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cert_path = rtr.router.cert_manager.cert_path(config.router_id)
        ssl_context.load_cert_chain(
            certfile=cert_path,
            keyfile=cert_path.replace(".crt", ".key")
        )
        rtr.socket = ssl_context.wrap_socket(rtr.socket, server_side=True)
        rtr.thread = threading.Thread(target=serve, args=(rtr, ))
        rtr.thread.start()

        if config.bootstrap_nodes is not None and len(config.bootstrap_nodes) > 0:
            for n in config.bootstrap_nodes:
                try:
                    rtr.router.bootstrap(n)
                    break # Throws exception if connection is not made
                except Exception as e:
                    print(e)

        return rtr

