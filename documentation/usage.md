## Usage Examples

### Basic Setup

```python
from distributed_state_network import DSNodeServer, DSNodeConfig, Endpoint

# Create configuration
config = DSNodeConfig(
    node_id="node1",
    port=8000,
    aes_key_file="/path/to/shared.key",
    bootstrap_nodes=[]  # Empty for first node
)

# Start server
server = DSNodeServer.start(config)

# Update state
server.node.update_data("status", "online")
server.node.update_data("version", "1.0.0")

# Read own state
my_status = server.node.read_data("node1", "status")

# Get connected peers
peers = server.node.peers()
print(f"Connected peers: {peers}")

# Shutdown
server.stop()
```

### Joining Existing Network

```python
# Node 2 configuration with bootstrap
config2 = DSNodeConfig(
    node_id="node2",
    port=8001,
    aes_key_file="/path/to/shared.key",  # Same key file as network
    bootstrap_nodes=[
        Endpoint("127.0.0.1", 8000)  # Node 1's endpoint
    ]
)

server2 = DSNodeServer.start(config2)

# Read state from peer
peer_status = server2.node.read_data("node1", "status")
```

### With Disconnect Callback

```python
def handle_disconnect():
    print("A peer has disconnected!")
    # Handle reconnection logic

config = DSNodeConfig(
    node_id="node3",
    port=8002,
    aes_key_file="/path/to/shared.key",
    bootstrap_nodes=[Endpoint("127.0.0.1", 8000)]
)

server = DSNodeServer.start(config, disconnect_callback=handle_disconnect)
```

### With Update Callback

```python
def handle_update():
    print("A peer has updated!")

config = DSNodeConfig(
    node_id="node3",
    port=8002,
    aes_key_file="/path/to/shared.key",
    bootstrap_nodes=[Endpoint("127.0.0.1", 8000)]
)

server = DSNodeServer.start(config, update_callback=handle_update)
```