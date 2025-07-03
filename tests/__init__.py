import os
import sys
import ssl
import time
import ctypes
import random
import unittest
import threading

sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from distributed_state_network.handler import RouterServer

current_port = 8000
routers = []

def stop_thread(thread: threading.Thread):
    thread_id = thread.ident
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id,
            ctypes.py_object(SystemExit))
    if res > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
        print('Exception raise failure')

def serve(httpd):
    httpd.serve_forever()

def spawn_router(rtr_id: str, ver: str = "1.0.0"):
    global current_port
    current_port += 1
    httpd = RouterServer(rtr_id, current_port, ver)
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    cert_path = httpd.router.cert_manager.cert_path(rtr_id)
    ssl_context.load_cert_chain(
        certfile=cert_path,
        keyfile=cert_path.replace(".crt", ".key")
    )
    httpd.socket = ssl_context.wrap_socket(httpd.socket, server_side=True)
    t = threading.Thread(target=serve, args=(httpd, ))
    t.start()
    global routers
    routers.append((httpd, t))
    return httpd.router

def stop_router(rtr_id: str, remove: bool = True):
    global routers
    i = 0
    found = False
    for httpd, t in routers:
        if httpd.router.router_id == rtr_id:
            httpd.router.shutting_down = True
            httpd.socket.close()
            stop_thread(t)
            found = True
            break
        i += 1
    if found:
        if remove:
            del routers[i]
    else:
        raise Exception(f"Could not stop router {rtr_id}")
    
class TestRouter(unittest.TestCase):
    def tearDown(self):
        global routers
        for httpd, t in routers:
            stop_router(httpd.router.router_id, False)
        routers = []

    def test_single(self):
        spawn_router("one")

    def test_double(self):
        bootstrap = spawn_router("bootstrap")
        connector = spawn_router("connector")
        connector.bootstrap(bootstrap.my_con())
        self.assertIn("connector", list(bootstrap.peers()))
        self.assertIn("bootstrap", list(bootstrap.peers()))

        self.assertIn("connector", list(connector.peers()))
        self.assertIn("bootstrap", list(connector.peers()))

    def test_many(self):
        bootsrap = spawn_router("bootstrap")
        connectors = [spawn_router(f"node-{i}") for i in range(0, 10)]
        for c in connectors:
            c.bootstrap(bootsrap.my_con())

        boot_peers = list(bootsrap.peers())

        for c in connectors:
            peers = c.peers()
            self.assertIn(c.router_id, boot_peers)
            self.assertIn("bootstrap", list(peers))
            for i in range(0, 10):
                self.assertIn(f"node-{i}", list(peers))

    def test_multi_bootstrap(self):
        bootstraps = [spawn_router(f"bootstrap-{i}") for i in range(0, 3)]
        for i in range(1, len(bootstraps)):
            bootstraps[i].bootstrap(bootstraps[i-1].my_con())
        
        connectors = []
        for bs in bootstraps:
            new_connectors = [spawn_router(f"node-{i}") for i in range(len(connectors), len(connectors) + 3)]
            for c in new_connectors:
                c.bootstrap(bs.my_con())
        
            connectors.extend(new_connectors)
        
        for ci in connectors:
            peers = ci.peers()
            for cj in connectors:
                self.assertIn(cj.router_id, peers)
            for b in bootstraps:
                self.assertIn(b.router_id, peers)
        
        for bi in bootstraps:
            peers = b.peers()
            for bj in bootstraps:
                self.assertIn(c.router_id, peers)
            
            for c in connectors:
                self.assertIn(c.router_id, peers)

    def test_reconnect(self):
        bootstrap = spawn_router("bootstrap")
        connector = spawn_router("connector")
        connector.bootstrap(bootstrap.my_con())
        self.assertIn(connector.router_id, bootstrap.peers())
        stop_router("connector")
        time.sleep(6)
        self.assertNotIn(connector.router_id, bootstrap.peers())

    def test_churn(self):
        bootstrap = spawn_router("bootstrap")
        
        stopped = []
        connectors = []
        network_labels = ["bootstrap"]
        for i in range(5):
            new_connectors = [spawn_router(f"node-{i}") for i in range(len(connectors), len(connectors) + 5)]
            connectors.extend(new_connectors)
            for c in new_connectors:
                c.bootstrap(bootstrap.my_con())
                network_labels.append(c.router_id)
            to_shutdown = random.choice(new_connectors)
            stop_router(to_shutdown.router_id)
            network_labels.remove(to_shutdown.router_id)
            stopped.append(to_shutdown)
            time.sleep(6)
            for c in connectors:
                if c.router_id not in network_labels:
                    continue
                self.assertEqual(network_labels, list(c.peers()))

    def test_state(self):
        bootstrap = spawn_router("bootstrap")
        connector = spawn_router("connector")
        connector.bootstrap(bootstrap.my_con())
        connector.update_data("foo", "bar")
        self.assertEqual("bar", bootstrap.read_data("connector", "foo"))
        bootstrap.update_data("bar", "baz")
        self.assertEqual("baz", connector.read_data("bootstrap", "bar"))

if __name__ == "__main__":
    unittest.main()