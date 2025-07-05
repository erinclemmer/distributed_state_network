# Distributed State Network

This python package is to help create distributed applications. All nodes in the network have a key-value database that they can write to that other nodes can read without sending a request for that information whenever it is needed. We call this a state database and each node can save information to their own database but not change other nodes data.

## Setup
This is intended to be used as a middleware for another application rather than stand-alone. To start a node server import it from the package and start it with a configuration.

```python
from distributed_state_network import DSNodeServer, DSNodeConfig



```