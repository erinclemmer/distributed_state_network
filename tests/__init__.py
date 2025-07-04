import os
import sys
import ssl
import time
import ctypes
import random
import logging
import unittest
import threading
from typing import List

sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from distributed_state_network.objects.config import RouterConfig
from distributed_state_network.handler import RouterServer
from distributed_state_network.objects.endpoint import Endpoint

current_port = 8000
routers = []

if not os.path.exists("test.key"):
    RouterServer.generate_key("test.key")

def serve(httpd):
    httpd.serve_forever()

def spawn_router(rtr_id: str, bootstrap_nodes: List[Endpoint] = []):
    global current_port
    current_port += 1
    rtr = RouterServer.start(RouterConfig(rtr_id, current_port, "test.key", bootstrap_nodes))
    global routers
    routers.append(rtr)
    return rtr

class TestRouter(unittest.TestCase):
    def tearDown(self):
        global routers
        for rtr in routers:
            rtr.stop()
        routers = []

    def test_single(self):
        spawn_router("one")

    def test_double(self):
        bootstrap = spawn_router("bootstrap")
        connector = spawn_router("connector", [bootstrap.router.my_con()])
        self.assertIn("connector", list(bootstrap.router.peers()))
        self.assertIn("bootstrap", list(bootstrap.router.peers()))

        self.assertIn("connector", list(connector.router.peers()))
        self.assertIn("bootstrap", list(connector.router.peers()))

    def test_many(self):
        bootstrap = spawn_router("bootstrap")
        connectors = [spawn_router(f"node-{i}", [bootstrap.router.my_con()]) for i in range(0, 10)]

        boot_peers = list(bootstrap.router.peers())

        for c in connectors:
            peers = c.router.peers()
            self.assertIn(c.config.router_id, boot_peers)
            self.assertIn("bootstrap", list(peers))
            for i in range(0, 10):
                self.assertIn(f"node-{i}", list(peers))

    def test_multi_bootstrap(self):
        bootstraps = [spawn_router(f"bootstrap-{i}") for i in range(0, 3)]
        for i in range(1, len(bootstraps)):
            bootstraps[i].router.bootstrap(bootstraps[i-1].router.my_con())
        
        connectors = []
        for bs in bootstraps:
            new_connectors = [spawn_router(f"node-{i}", [bs.router.my_con()]) for i in range(len(connectors), len(connectors) + 3)]
        
            connectors.extend(new_connectors)
        
        for ci in connectors:
            peers = ci.router.peers()
            for cj in connectors:
                self.assertIn(cj.config.router_id, peers)
            for b in bootstraps:
                self.assertIn(b.config.router_id, peers)
        
        for bi in bootstraps:
            peers = b.router.peers()
            for bj in bootstraps:
                self.assertIn(bj.config.router_id, peers)
            
            for c in connectors:
                self.assertIn(c.config.router_id, peers)

    def test_reconnect(self):
        bootstrap = spawn_router("bootstrap")
        connector = spawn_router("connector", [bootstrap.router.my_con()])
        self.assertIn(connector.config.router_id, bootstrap.router.peers())
        connector.stop()
        time.sleep(10)
        self.assertNotIn(connector.config.router_id, bootstrap.router.peers())

    def test_churn(self):
        bootstrap = spawn_router("bootstrap")
        
        stopped = []
        connectors = []
        network_labels = ["bootstrap"]
        for i in range(5):
            new_connectors = [spawn_router(f"node-{i}", [bootstrap.router.my_con()]) for i in range(len(connectors), len(connectors) + 5)]
            connectors.extend(new_connectors)
            for c in new_connectors:
                network_labels.append(c.config.router_id)
            to_shutdown = random.choice(new_connectors)
            to_shutdown.stop()
            network_labels.remove(to_shutdown.config.router_id)
            stopped.append(to_shutdown)
            time.sleep(6)
            for c in connectors:
                if c.config.router_id not in network_labels:
                    continue
                self.assertEqual(sorted(network_labels), sorted(list(c.router.peers())))

    def test_state(self):
        bootstrap = spawn_router("bootstrap")
        connector = spawn_router("connector", [bootstrap.router.my_con()])
        connector.router.update_data("foo", "bar")
        self.assertEqual("bar", bootstrap.router.read_data("connector", "foo"))
        bootstrap.router.update_data("bar", "baz")
        self.assertEqual("baz", connector.router.read_data("bootstrap", "bar"))

if __name__ == "__main__":
    unittest.main()