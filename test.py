import os
import sys
import ssl
import time
import ctypes
import random
import shutil
import logging
import unittest
import threading
import requests
from typing import List

sys.path.append(os.path.join(os.path.dirname(__file__), './src'))

from distributed_state_network import DSNodeServer, Endpoint, DSNodeConfig
from distributed_state_network.objects.state import NodeState
from distributed_state_network.objects.packets import HelloPacket, BootstrapPacket
from distributed_state_network.util.aes import generate_aes_key

current_port = 8000
nodes = []

if os.path.exists('certs'):
    shutil.rmtree('certs')
key_file = "src/distributed_state_network/test.key"

if not os.path.exists(key_file):
    DSNodeServer.generate_key(key_file)

def serve(httpd):
    httpd.serve_forever()

def spawn_node(node_id: str, bootstrap_nodes: List[Endpoint] = []):
    global current_port
    current_port += 1
    n = DSNodeServer.start(DSNodeConfig(node_id, current_port, key_file, bootstrap_nodes))
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

    @unittest.skip("")
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

        self.assertEqual(None, bootstrap.node.read_data("connector", "foo"))

        connector.node.update_data("foo", "bar")
        self.assertEqual("bar", bootstrap.node.read_data("connector", "foo"))
        bootstrap.node.update_data("bar", "baz")
        self.assertEqual("baz", connector.node.read_data("bootstrap", "bar"))

    def test_bad_aes_key(self):
        try:
            DSNodeServer.start(DSNodeConfig("bad key test", 8080, "bad.key", []))
            self.fail("Should throw error before this")
        except Exception as e:
            print(e)

    def test_authorization(self):
        n = spawn_node("node")
        res = requests.post(f"https://127.0.0.1:{n.config.port}/ping", data=b'TEST', verify=False)
        self.assertEqual(res.content, b'Not Authorized')

        encrypted_data = n.node.encrypt_data(b'TEST')
        res = requests.post(f"https://127.0.0.1:{n.config.port}/ping", data=encrypted_data, verify=False)
        self.assertEqual(res.content, b'')

    def test_version_matching(self):
        bootstrap = spawn_node("bootstrap")
        bootstrap.node.node_states["bootstrap"].version = "bad_version"
        try:
            connector = spawn_node("connector", [bootstrap.node.my_con()])
            self.fail("Should throw error when connecting")
        except Exception as e:
            print(e)

    def test_status_code(self):
        bootstrap = spawn_node("bootstrap")
        connector = spawn_node("connector", [bootstrap.node.my_con()])
        try:
            connector.node.send_request_to_node("bootstrap", "bad-path", b'', False)
            self.fail("Should error if a 404 was received")
        except Exception as e:
            print(e)

    def test_bad_req_data(self):
        bootstrap = spawn_node("bootstrap")
        connector = spawn_node("connector", [bootstrap.node.my_con()])
        try: 
            connector.node.send_request_to_node("bootstrap", "hello", b'TEST', False)
            self.fail("Should throw error for malformed data")
        except Exception as e:
            print(e)

    def test_decrypt_response(self):
        n = spawn_node("node")
        sample_response = requests.get("https://google.com")
        try:
            n.node.parse_response(("test", 3000), "test", sample_response)
            self.fail("Should throw error if can't decrypt response")
        except Exception as e:
            print(e)

    def test_bad_update(self):
        bootstrap = spawn_node("bootstrap")
        connector = spawn_node("connector", [bootstrap.node.my_con()])

        state = NodeState("bootstrap", bootstrap.node.my_con(), bootstrap.node.my_version(), time.time(), { })
        try: 
            bootstrap.node.handle_update(state.to_bytes())
            self.fail("Node should not handle updates for itself")
        except Exception as e:
            print(e)
            self.assertEqual(e.args[0], "Received update for our own node")
        time_before = time.time() - 10
        state = NodeState("connector", bootstrap.node.my_con(), bootstrap.node.my_version(), time_before, { })
        try: 
            bootstrap.node.handle_update(state.to_bytes())
            self.fail("Node should only accept update packets that are newer than the version we have")
        except Exception as e:
            print(e)
            self.assertEqual(e.args[0], "Received outdated update packet")
    
    def test_bad_hello(self):
        bootstrap = spawn_node("bootstrap")
        connector_0 = spawn_node("connector-0", [bootstrap.node.my_con()])
        connector_0.stop()
        connector_1 = spawn_node("connector-1", [bootstrap.node.my_con()])
        self.assertEqual(connector_1.node.peers(), ["bootstrap", "connector-1"])

    def test_connection_from_node(self):
        n0 = spawn_node("node-0")
        n1 = spawn_node("node-1", [n0.node.my_con()])
        _, port = n0.node.connection_from_node("node-1")
        self.assertEqual(port, n1.config.port)
        try:
            n0.node.connection_from_node("test")
            self.fail("Should throw error if it can't find a matching node")
        except Exception as e:
            print(e)

    def test_get_certificate(self):
        n = spawn_node("node")
        self.assertEqual(n.node.public_key_file(), "certs/node/node.crt")
        self.assertEqual(n.node.private_key_file(), "certs/node/node.key")
        self.assertIsNone(n.node.get_certificate("Bad-Node"))

    def test_config_dict(self):
        config_dict = {
            "node_id": "node",
            "port": 8000,
            "aes_key_file": "test.key",
            "bootstrap_nodes": [
                {
                    "address": "127.0.0.1",
                    "port": 8001
                }
            ]
        }

        config = DSNodeConfig.from_dict(config_dict)
        self.assertEqual(config_dict["node_id"], config.node_id)
        self.assertEqual(config_dict["port"], config.port)
        self.assertEqual(config_dict["aes_key_file"], config.aes_key_file)
        self.assertTrue(len(config.bootstrap_nodes) > 0)
        self.assertEqual(config_dict["bootstrap_nodes"][0]["address"], config.bootstrap_nodes[0].address)
        self.assertEqual(config_dict["bootstrap_nodes"][0]["port"], config.bootstrap_nodes[0].port)

    def test_bad_packets(self):
        try:
            BootstrapPacket.from_bytes(b'')
            self.fail("Should throw error on bad parse")
        except Exception as e:
            print(e)

        try:
            BootstrapPacket.from_bytes(b'Random Data')
            self.fail("Should throw error on bad parse")
        except Exception as e:
            print(e)

        try:
            HelloPacket.from_bytes(b'')
            self.fail("Should throw error on bad parse")
        except Exception as e:
            print(e)

        try:
            HelloPacket.from_bytes(b'Random data')
            self.fail("Should throw error on bad parse")
        except Exception as e:
            print(e)

        try:
            NodeState.from_bytes(b'')
            self.fail("Should throw error on bad parse")
        except Exception as e:
            print(e)

        try:
            NodeState.from_bytes(b'Random data')
            self.fail("Should throw error on bad parse")
        except Exception as e:
            print(e)

    def test_aes(self):
        key = generate_aes_key()
        self.assertEqual(32, len(key))

if __name__ == "__main__":
    unittest.main()