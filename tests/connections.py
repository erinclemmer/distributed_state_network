import os
import sys
import time
import unittest
from typing import Optional, Callable

sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from distributed_state_network import DSNodeServer, DSNodeConfig, Endpoint

KEY_FILE = "network.key"

if not os.path.exists(KEY_FILE):
    DSNodeServer.generate_key("network.key")

d_cb_test = 0

current_port = 5000

def start_node(node_id: str, bootstrap_port: int = None, disconnect_cb: Optional[Callable] = None):
    global current_port
    args = {
        "node_id": node_id,
        "port": current_port,
        "aes_key_file": KEY_FILE
    }
    current_port += 1
    if bootstrap_port is not None:
        args["bootstrap_nodes"] = [Endpoint(
            address="127.0.0.1",
            port=bootstrap_port
        )]
    else:
        args["bootstrap_nodes"] = []

    return DSNodeServer.start(DSNodeConfig(**args), disconnect_cb)

class ConnectionsTest(unittest.TestCase):
    def test_one(self):
        node = start_node("node-1")
        self.assertEqual(["node-1"], node.node.peers())

    def test_two(self):
        node1 = start_node("node-1")
        node2 = start_node("node-2", node1.config.port)
        self.assertEqual(["node-1", "node-2"], sorted(node1.node.peers()))
        self.assertEqual(["node-1", "node-2"], sorted(node2.node.peers()))

    def test_many(self):
        bootstrap_node = start_node("bootstrap")
        nodes = []
        for i in range(10):
            nodes.append(start_node(f"node-{i}", bootstrap_node.config.port))

        node_list = ["bootstrap"]
        node_list.extend([f"node-{i}" for i in range(10)])

        time.sleep(5)
        self.assertEqual(node_list, sorted(bootstrap_node.node.peers()))
        for i in range(10):
            self.assertEqual(node_list, sorted(nodes[i].node.peers()))

    def test_disconnect(self):
        node1 = start_node("node-1")
        node2 = start_node("node-2", node1.config.port)
        node3 = start_node("node-3", node1.config.port)

        time.sleep(1)
        node2.stop()
        time.sleep(10)
        node4 = start_node("node-4", node1.config.port)
        time.sleep(10)
        self.assertEqual(["node-1", "node-3", "node-4"], sorted(node1.node.peers()))
        self.assertEqual(["node-1", "node-3", "node-4"], sorted(node3.node.peers()))
        self.assertEqual(["node-1", "node-3", "node-4"], sorted(node4.node.peers()))

    def test_disconnect_cb(self):
        global d_cb_test
        d_cb_test = 0
        def inc():
            global d_cb_test
            d_cb_test = 1
        node1 = start_node("node-1", None, inc)
        node2 = start_node("node-2", node1.config.port)
        time.sleep(1)
        node2.stop()
        time.sleep(5)
        self.assertEqual(d_cb_test, 1)

if __name__ == '__main__':
    unittest.main()