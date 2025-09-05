## DSNodeServer

HTTPS server wrapper for DSNode that handles incoming network requests.

```python
from distributed_state_network import DSNodeServer
```

### Class Definition
```python
class DSNodeServer(HTTPServer):
    config: DSNodeConfig
    node: DSNode
```

### Constructor

**Parameters:**
- `config` (`DSNodeConfig`): Node configuration
- `disconnect_callback` (`Optional[Callable]`): Callback for disconnect events
- `update_callback` (`Optional[Callable]`): Callback for state update events

### Static Methods

### `start(config: DSNodeConfig, disconnect_callback: Optional[Callable] = None, update_callback: Optional[Callable] = None) -> DSNodeServer`
Creates and starts a new DSNodeServer instance with SSL configuration.
```python
server = DSNodeServer.start(config)
```

**Parameters:**
- `config` (`DSNodeConfig`): Node configuration
- `disconnect_callback` (`Optional[Callable]`): Callback for disconnect events
- `update_callback` (`Optional[Callable]`): Callback for state update events

**Returns:**
- `DSNodeServer`: Running server instance

### `generate_key(out_file_path: str) -> None`
Generates a new AES key file for network encryption.

**Parameters:**
- `out_file_path` (`str`): Path where the key file will be saved

**Example:**
```python
DSNodeServer.generate_key("/path/to/network.key")
```

### Instance Methods

### `stop() -> None`
Gracefully shuts down the server and cleans up resources.

**Example:**
```python
server.stop()
```