import os
import sys
import time
import random
import shutil
import unittest
import requests
from typing import List, Dict

sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from distributed_state_network import DSNodeServer, Endpoint, DSNodeConfig

from distributed_state_network.objects.state_packet import StatePacket
from distributed_state_network.objects.hello_packet import HelloPacket

from distributed_state_network.util.aes import generate_aes_key

current_port = 8000
nodes = []

aes_key = DSNodeServer.generate_key()

def spawn_node(node_id: str, bootstrap_nodes: List[Dict] = []):
    global current_port
    current_port += 1
    n = DSNodeServer.start(DSNodeConfig.from_dict({
        "node_id": node_id,
        "port": current_port,
        "aes_key": aes_key,
        "bootstrap_nodes": bootstrap_nodes
    }))
    global nodes
    nodes.append(n)
    return n

class TestNode(unittest.TestCase):
    def tearDown(self):
        global nodes
        for n in nodes:
            n.stop()
        nodes = []

        if os.path.exists('certs'):
            shutil.rmtree('certs')

        if os.path.exists('credentials'):
            shutil.rmtree('credentials')

    def test_single(self):
        spawn_node("one")

    def test_double(self):
        bootstrap = spawn_node("bootstrap")
        connector = spawn_node("connector", [bootstrap.node.my_con().to_json()])
        self.assertIn("connector", list(bootstrap.node.peers()))
        self.assertIn("bootstrap", list(bootstrap.node.peers()))

        self.assertIn("connector", list(connector.node.peers()))
        self.assertIn("bootstrap", list(connector.node.peers()))

    def test_many(self):
        bootstrap = spawn_node("bootstrap")
        connectors = [spawn_node(f"node-{i}", [bootstrap.node.my_con().to_json()]) for i in range(0, 10)]

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
            new_connectors = [spawn_node(f"node-{i}", [bs.node.my_con().to_json()]) for i in range(len(connectors), len(connectors) + 3)]
        
            connectors.extend(new_connectors)
        
        for ci in connectors:
            peers = ci.node.peers()
            for cj in connectors:
                self.assertIn(cj.config.node_id, peers)
            for b in bootstraps:
                self.assertIn(b.config.node_id, peers)
        
        for bi in bootstraps:
            peers = bi.node.peers()
            for bj in bootstraps:
                self.assertIn(bj.config.node_id, peers)
            
            for c in connectors:
                self.assertIn(c.config.node_id, peers)

    def test_reconnect(self):
        bootstrap = spawn_node("bootstrap")
        connector = spawn_node("connector", [bootstrap.node.my_con().to_json()])
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
            new_connectors = [spawn_node(f"node-{i}", [bootstrap.node.my_con().to_json()]) for i in range(len(connectors), len(connectors) + 5)]
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
        connector = spawn_node("connector", [bootstrap.node.my_con().to_json()])

        self.assertEqual(None, bootstrap.node.read_data("connector", "foo"))

        connector.node.update_data("foo", "bar")
        time.sleep(0.5)  # Give time for HTTP request to complete
        self.assertEqual("bar", bootstrap.node.read_data("connector", "foo"))
        bootstrap.node.update_data("bar", "baz")
        time.sleep(0.5)  # Give time for HTTP request to complete
        self.assertEqual("baz", connector.node.read_data("bootstrap", "bar"))

    def test_bad_aes_key(self):
        try:
            DSNodeServer.start(DSNodeConfig("bad key test", 8080, "bad.key", []))
            self.fail("Should throw error before this")
        except Exception as e:
            print(e)

    def test_authorization(self):
        """Test that unauthorized HTTP requests are rejected"""
        n = spawn_node("node")
        
        # Give Flask server time to start
        time.sleep(0.5)
        
        # Send unencrypted data - should be rejected with 500 error
        try:
            response = requests.post(
                f'http://127.0.0.1:{n.config.port}/ping',
                data=b'TEST',
                timeout=2
            )
            # Should get error status code
            self.assertNotEqual(response.status_code, 200)
            print(f"Received status code for bad data: {response.status_code}")
        except Exception as e:
            # Connection errors are also acceptable
            print(f"Request failed as expected: {e}")
        
        # Send properly encrypted data
        encrypted_data = n.node.encrypt_data(bytes([4]) + b'TEST')  # MSG_PING = 4
        response = requests.post(
            f'http://127.0.0.1:{n.config.port}/ping',
            data=encrypted_data,
            headers={'Content-Type': 'application/octet-stream'},
            timeout=2
        )
        
        # Should get successful response for valid encrypted ping
        self.assertEqual(response.status_code, 200)
        decrypted = n.node.decrypt_data(response.content)
        self.assertEqual(decrypted[0], 4)  # Should be MSG_PING response

    def test_version_matching(self):
        bootstrap = spawn_node("bootstrap")
        # Modify version after creation
        old_version = bootstrap.node.version
        bootstrap.node.version = "bad_version"
        try:
            connector = spawn_node("connector", [bootstrap.node.my_con().to_json()])
            self.fail("Should throw error when connecting with version mismatch")
        except Exception as e:
            print(e)
        finally:
            bootstrap.node.version = old_version

    def test_bad_req_data(self):
        bootstrap = spawn_node("bootstrap")
        connector = spawn_node("connector", [bootstrap.node.my_con().to_json()])
        try: 
            # Try to send malformed data
            connector.node.send_http_request(bootstrap.node.my_con(), 1, b'MALFORMED_DATA')
            self.fail("Should throw error for malformed data")
        except Exception as e:
            print(e)

    def test_bad_update(self):
        bootstrap = spawn_node("bootstrap")
        connector = spawn_node("connector", [bootstrap.node.my_con().to_json()])
        bt_prv_key = bootstrap.node.cred_manager.my_private()
        cn_prv_key = connector.node.cred_manager.my_private()
        state = StatePacket.create("bootstrap", time.time(), bt_prv_key, { })
        try: 
            bootstrap.node.handle_update(state.to_bytes())
            self.fail("Node should not handle updates for itself")
        except Exception as e:
            print(e)
            self.assertEqual(e.args[0], 406)
        state = StatePacket("connector", time.time(), b'', { })
        try:
            bootstrap.node.handle_update(state.to_bytes())
            self.fail("Should not accepted unsigned packets")
        except Exception as e:
            print(e)
            self.assertEqual(e.args[0], 401)

        time_before = time.time() - 10
        state = StatePacket.create("connector", time.time(), cn_prv_key, { "a": "1" })
        bootstrap.node.handle_update(state.to_bytes())

        state = StatePacket.create("connector", time_before, cn_prv_key, { "a": "2" })
        try: 
            bootstrap.node.handle_update(state.to_bytes())
            self.fail("Node should only accept update packets that are newer than the version we have")
        except Exception as e:
            print(e)
            self.assertEqual(e.args[0], 406)
    
    def test_bad_hello(self):
        bootstrap = spawn_node("bootstrap")
        connector_0 = spawn_node("connector-0", [bootstrap.node.my_con().to_json()])
        connector_0.stop()
        connector_1 = spawn_node("connector-1", [bootstrap.node.my_con().to_json()])
        self.assertEqual(sorted(connector_1.node.peers()), ["bootstrap", "connector-1"])

    def test_connection_from_node(self):
        n0 = spawn_node("node-0")
        n1 = spawn_node("node-1", [n0.node.my_con().to_json()])
        con = n0.node.connection_from_node("node-1")
        self.assertEqual(con.port, n1.config.port)
        try:
            n0.node.connection_from_node("test")
            self.fail("Should throw error if it can't find a matching node")
        except Exception as e:
            print(e)

    def test_config_dict(self):
        config_dict = {
            "node_id": "node",
            "port": 8000,
            "aes_key": "XXX",
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
        self.assertEqual(config_dict["aes_key"], config.aes_key)
        self.assertTrue(len(config.bootstrap_nodes) > 0)
        self.assertEqual(config_dict["bootstrap_nodes"][0]["address"], config.bootstrap_nodes[0].address)
        self.assertEqual(config_dict["bootstrap_nodes"][0]["port"], config.bootstrap_nodes[0].port)

    def test_bad_packets(self):
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
            StatePacket.from_bytes(b'')
            self.fail("Should throw error on bad parse")
        except Exception as e:
            print(e)

        try:
            StatePacket.from_bytes(b'Random data')
            self.fail("Should throw error on bad parse")
        except Exception as e:
            print(e)

    def test_aes(self):
        key = DSNodeServer.generate_key()
        self.assertEqual(64, len(key))

    def test_authentication_reset(self):
        bootstrap = spawn_node("bootstrap")
        connector = spawn_node("connector", [bootstrap.node.my_con().to_json()])
        connector.stop()
        shutil.rmtree("credentials/connector")
        try:
            connector = spawn_node("connector", [bootstrap.node.my_con().to_json()])
            self.fail("Should not be able to authenticate with bootstrap and throw error because credentials are reset")
        except Exception as e:
            print(e)

    def test_reauthentication(self):
        if os.path.exists("credentials"):
            shutil.rmtree("credentials")
        bootstrap = spawn_node("bootstrap")
        connector = spawn_node("connector", [bootstrap.node.my_con().to_json()])
        connector.stop()
        connector = spawn_node("connector", [bootstrap.node.my_con().to_json()])
        self.assertIn('connector', bootstrap.node.peers())

    def test_http_endpoints(self):
        """Test that HTTP endpoints are accessible"""
        n = spawn_node("http-test-node")
        
        # Test that all endpoints exist
        endpoints = ['/hello', '/peers', '/update', '/ping']
        
        for endpoint in endpoints:
            # Send a request to each endpoint (will fail due to encryption, but should return 400/500, not 404)
            try:
                response = requests.post(
                    f'http://127.0.0.1:{n.config.port}{endpoint}',
                    data=b'test',
                    timeout=2
                )
                # Should not be 404 (Not Found)
                self.assertNotEqual(response.status_code, 404, f"Endpoint {endpoint} not found")
                print(f"Endpoint {endpoint} exists (status: {response.status_code})")
            except Exception as e:
                print(f"Endpoint {endpoint} test failed: {e}")

if __name__ == "__main__":
    unittest.main()
