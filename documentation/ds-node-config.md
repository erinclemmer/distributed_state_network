## DSNodeConfig

Configuration object for initializing a DSNode instance.

```python
from distributed_state_network import DSNodeConfig
```

### Class Definition
```python
@dataclass(frozen=True)
class DSNodeConfig:
    node_id: str
    port: int
    https: bool
    network_ip: str
    aes_key_file: str
    bootstrap_nodes: List[Endpoint]
```

### Attributes
- **node_id** (`str`): Unique identifier for the node
- **port** (`int`): Port number for the node to listen on
- **aes_key_file** (`str`): Path to the AES key file for encryption/decryption
- **https** (`bool`): whether to use HTTPS network requests (true) or http (false)
- **network_ip** (`str`): Must match network address of the current computer (only if https is on)
- **bootstrap_nodes** (`List[Endpoint]`): List of initial nodes to connect to when joining the network

### Methods

### `from_dict(data: Dict) -> DSNodeConfig`
Creates a DSNodeConfig instance from a dictionary.

**Parameters:**
- `data` (`Dict`): Dictionary containing configuration parameters

**Returns:**
- `DSNodeConfig`: Configuration instance

**Example:**
```python
config_dict = {
    "node_id": "node1",
    "port": 8000,
    "aes_key_file": "/path/to/key.aes",
    "https": false,
    "network_ip": "192.168.0.1",
    "bootstrap_nodes": [
        {"address": "127.0.0.1", "port": 8001}
    ]
}
config = DSNodeConfig.from_dict(config_dict)
```