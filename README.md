# Distributed State Network

A Python framework for building distributed applications where nodes automatically share state without explicit data requests.

## Why DSN?

Traditional distributed systems require constant polling or complex pub/sub mechanisms to share state between nodes. DSN solves this by providing:

- **Automatic state synchronization** - Changes propagate instantly across the network
- **No single point of failure** - Every node maintains its own state
- **Simple key-value interface** - Read any node's data as easily as local variables
- **Complete Security** - Triple-layer encryption protects your network

Perfect for building distributed monitoring systems, IoT networks, or any application where multiple machines need to share state efficiently.

## Installation

```bash
pip install distributed-state-network
```

## Quick Start

### 1. Create Your First Node

The simplest DSN network is a single node:

```python
from distributed_state_network import DSNodeServer, DSNodeConfig

# Generate a network key (do this once for your entire network)
DSNodeServer.generate_key("network.key")

# Start a node
node = DSNodeServer.start(DSNodeConfig(
    node_id="my_first_node",
    port=8000,
    aes_key_file="network.key",
    bootstrap_nodes=[]  # Empty for the first node
))

# Write some data
node.node.update_data("status", "online")
node.node.update_data("temperature", "72.5")
```

## How It Works

DSN creates a peer-to-peer network where each node maintains its own state database:

**Key concepts:**
- Each node owns its state and is the only one who can modify it
- State changes are automatically broadcast to all connected nodes
- Any node can read any other node's state instantly
- All communication is encrypted with AES + ECDSA + HTTPS

## API Reference

### Node Methods

**update_data(key, value)** - Update a key in this node's state
```python
node.update_data("sensor_reading", "42.0")
```

**read_data(node_id, key)** - Read a value from any node's state

```python
temperature = node.read_data("sensor_node", "temperature")
```

**peers()** - List all connected nodes
```python
connected_nodes = node.peers()
```

## Real-World Examples

### Distributed Temperature Monitoring

Create a network of temperature sensors that share readings:

```python
# On each Raspberry Pi with a sensor:
sensor_node = DSNodeServer.start(DSNodeConfig(
    node_id=f"sensor_{location}",
    port=8000,
    aes_key_file="network.key",
    bootstrap_nodes=[{"address": "coordinator.local", "port": 8000}]
))

# Continuously update temperature
while True:
    temp = read_temperature_sensor()
    sensor_node.node.update_data("temperature", str(temp))
    sensor_node.node.update_data("timestamp", str(time.time()))
    time.sleep(60)
```

On the monitoring station:
```python
for node_id in monitor.node.peers():
    if node_id.startswith("sensor_"):
        temp = monitor.node.read_data(node_id, "temperature")
        print(f"{node_id}: {temp}°F")
```

## Troubleshooting

### Node Can't Connect
- Verify the AES key file is identical on all nodes
- Check firewall rules allow traffic on the configured port
- Ensure bootstrap node address is reachable

### State Not Updating
- Confirm nodes show as connected with `node.peers()`
- Check network latency between nodes
- Verify no duplicate node IDs (each must be unique)

## Performance Characteristics
- State updates typically propagate in <100ms on local networks
- Each node stores the complete state of all other nodes
- Suitable for networks up to ~100 nodes
- State values should be kept reasonably small (< 1MB per key)