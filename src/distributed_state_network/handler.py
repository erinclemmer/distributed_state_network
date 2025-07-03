import ssl
import threading
import json
from typing import Tuple
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

from distributed_state_network.router import Router
from distributed_state_network.config import RouterConfig

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
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            _send_403(self, "Invalid JSON")
            return

        if self.server.router.shutting_down:
            _respond_bytes(self, b'DOWN')
            return

        if self.path == "/bootstrap":
            res = self.server.router.handle_bootstrap(data)
            _respond_bytes(self, res)

        if self.path == "/hello":
            res = self.server.router.handle_hello(data)
            _respond_bytes(self, res)

        if self.path == "/update":
            Thread(target=self.server.router.handle_update, args=(data, )).start()
            _respond_bytes(self, b'')

        if self.path == "/ping":
            _respond_bytes(self, b'')

    def log_message(self, format, *args):
        pass

def serve(httpd):
    httpd.serve_forever()

class RouterServer(HTTPServer):
    def __init__(
        self, 
        router_id: str,
        port: int,
        version: str,
        aes_key_file: str
    ):
        super().__init__(("127.0.0.1", port), RouterHandler)
        self.router = Router(router_id, port, version, aes_key_file)
        self.router.logger.info(f'Started Router on port {port}')

    def stop(self):
        self.shutdown()
        self.router.shutting_down = True
        self.socket.close()

    @staticmethod 
    def start(config: RouterConfig, version: str) -> Tuple[Thread, 'RouterServer']:
        httpd = RouterServer(config.router_id, config.port, version, config.aes_key_file)
        if (len(config.bootstrap_nodes) > 0):
            bootstrap = config.bootstrap_nodes[0]
            httpd.router.bootstrap((bootstrap.address, bootstrap.port))
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cert_path = httpd.router.cert_manager.cert_path(config.router_id)
        ssl_context.load_cert_chain(
            certfile=cert_path,
            keyfile=cert_path.replace(".crt", ".key")
        )
        httpd.socket = ssl_context.wrap_socket(httpd.socket, server_side=True)
        httpd_thread = threading.Thread(target=serve, args=(httpd, ))
        httpd_thread.start()

        return httpd_thread, httpd
