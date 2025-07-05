# Distributed State Network
  
This python package is to help create distributed applications. All nodes in the network have a key-value database that they can write to that other nodes can read without sending a request for that information whenever it is needed. We call this a state database and each node can save information to their own database but not change other nodes data.  
  
## Setup
This is intended to be used as a middleware for another application rather than stand-alone. To start a node server import it from the package and start it with a configuration.  

```python
from distributed_state_network import DSNodeServer, DSNodeConfig

# Write a new aes key to the current directory
DSNodeServer.generate_key("test.key")

# Use the key to start a new network
bootstrap = DSNodeServer({
    "node_id": "bootstrap", # Network ID for the node
    "port": 8000, # Port to host the server on
    "aes_key_file": "test.key" # Key file for authentication to the network
})
```

First we use `DSNodeServer.generate_key` to write an aes key file that will be used for any node that wants to connect to the network. Then we start the first node up with a simple configuration, specifying the node's ID, port, and the location of the AES key file.  
  
To connect another node to we will copy the AES key file to the new machine and run this script.

**Note:** Each node ID is tied to a specific https key signature so every ID on the network must be unique.

```python
from distributed_state_network import DSNodeServer, DSNodeConfig

connector = DSNodeServer({
    "node_id": "connector", # New node ID
    "port": 8000, # Port to host the new server on
    "aes_key_file": "test.key", # Key file that was copied from first machine
    "bootstrap_nodes": [
        {
            # IP address of bootstrap node
            "address": "192.168.0.1",
            "port": 8000
        }
    ]
})
```

# Changing State Data

Now that both servers are connected to each other and are listening for updates we can update the database on one device and read it on another.

On the connector machine:
```python
connector.node.update_data("foo", "bar")
```

Then on the bootstrap machine:
```python
data = bootstrap.node.read_data("connector", "foo")
print(data)
```

This will produce the string "bar".

# Security
The package uses AES and HTTPS encryption together to protect against network attacks. Each network will have an AES key that authenticates them with the network. Any data traveling between nodes will be encrypted with that key. In addition to this, HTTPS encryption is also used to ensure that nodes send data to the correct destinations. When an authenticated node sends a request to another node, it verifies that the request was sent to the proper place by authenticating the request with a public key that was previously shared. This is explained in further detail in the bootstrap process.

# Bootstrap Process
