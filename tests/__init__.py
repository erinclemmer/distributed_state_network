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

from distributed_state_network import DSNodeServer, Endpoint, DSNodeConfig

current_port = 8000
nodes = []

key_file = "src/distributed_state_network/test.key"

if not os.path.exists(key_file):
    DSNodeServer.generate_key(key_file)

def serve(httpd):
    httpd.serve_forever()

def spawn_node(rtr_id: str, bootstrap_nodes: List[Endpoint] = []):
    global current_port
    current_port += 1
    n = DSNodeServer.start(DSNodeConfig(rtr_id, current_port, key_file, bootstrap_nodes))
    global nodes
    nodes.append(n)
    return n

class TestNode(unittest.TestCase):
    def tearDown(self):
        global nodes
        for n in nodes:
            n.stop()
        nodes = []

    def test_single(self):
        spawn_node("one")

    def test_double(self):
        bootstrap = spawn_node("bootstrap")
        connector = spawn_node("connector", [bootstrap.node.my_con()])
        self.assertIn("connector", list(bootstrap.node.peers()))
        self.assertIn("bootstrap", list(bootstrap.node.peers()))

        self.assertIn("connector", list(connector.node.peers()))
        self.assertIn("bootstrap", list(connector.node.peers()))

    def test_many(self):
        bootstrap = spawn_node("bootstrap")
        connectors = [spawn_node(f"node-{i}", [bootstrap.node.my_con()]) for i in range(0, 10)]

        boot_peers = list(bootstrap.node.peers())

        for c in connectors:
            peers = c.node.peers()
            self.assertIn(c.config.node_id, boot_peers)
            self.assertIn("bootstrap", list(peers))
            for i in range(0, 10):
                self.assertIn(f"node-{i}", list(peers))

    def test_multi_bootstrap(self):
        bootstraps = [spawn_node(f"bootstrap-{i}") for i in range(0, 3)]
        for i in range(1, len(bootstraps)):
            bootstraps[i].node.bootstrap(bootstraps[i-1].node.my_con())
        
        connectors = []
        for bs in bootstraps:
            new_connectors = [spawn_node(f"node-{i}", [bs.node.my_con()]) for i in range(len(connectors), len(connectors) + 3)]
        
            connectors.extend(new_connectors)
        
        for ci in connectors:
            peers = ci.node.peers()
            for cj in connectors:
                self.assertIn(cj.config.node_id, peers)
            for b in bootstraps:
                self.assertIn(b.config.node_id, peers)
        
        for bi in bootstraps:
            peers = b.node.peers()
            for bj in bootstraps:
                self.assertIn(bj.config.node_id, peers)
            
            for c in connectors:
                self.assertIn(c.config.node_id, peers)

    def test_reconnect(self):
        bootstrap = spawn_node("bootstrap")
        connector = spawn_node("connector", [bootstrap.node.my_con()])
        self.assertIn(connector.config.node_id, bootstrap.node.peers())
        connector.stop()
        time.sleep(10)
        self.assertNotIn(connector.config.node_id, bootstrap.node.peers())

    def test_churn(self):
        bootstrap = spawn_node("bootstrap")
        
        stopped = []
        connectors = []
        network_labels = ["bootstrap"]
        for i in range(5):
            new_connectors = [spawn_node(f"node-{i}", [bootstrap.node.my_con()]) for i in range(len(connectors), len(connectors) + 5)]
            connectors.extend(new_connectors)
            for c in new_connectors:
                network_labels.append(c.config.node_id)
            to_shutdown = random.choice(new_connectors)
            to_shutdown.stop()
            network_labels.remove(to_shutdown.config.node_id)
            stopped.append(to_shutdown)
            time.sleep(6)
            for c in connectors:
                if c.config.node_id not in network_labels:
                    continue
                self.assertEqual(sorted(network_labels), sorted(list(c.node.peers())))

    def test_state(self):
        bootstrap = spawn_node("bootstrap")
        connector = spawn_node("connector", [bootstrap.node.my_con()])
        connector.node.update_data("foo", "bar")
        self.assertEqual("bar", bootstrap.node.read_data("connector", "foo"))
        bootstrap.node.update_data("bar", "baz")
        self.assertEqual("baz", connector.node.read_data("bootstrap", "bar"))

if __name__ == "__main__":
    unittest.main()