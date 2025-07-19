# Distributed State Network
  
This python package is to help create distributed grid applications. All nodes in the network have a key-value database that they can write to that other nodes can read without sending a request for that information whenever it is needed. We call this a state database and each node can save information to their own database but not change other nodes data.  
  
## Setup
This is intended to be used as a middleware for another application rather than stand-alone. To start a node server import it from the package and start it with a configuration.  

```python
from distributed_state_network import DSNodeServer, DSNodeConfig

# Write a new aes key to the current directory
DSNodeServer.generate_key("test.key")

# Use the key to start a new network
bootstrap = DSNodeServer(DSNodeConfig(
    node_id="bootstrap", # Network ID for the node
    port=8000, # Port to host the server on
    aes_key_file="test.key" # Key file for authentication to the network
))
```

First we use `DSNodeServer.generate_key` to write an aes key file that will be used for any node that wants to connect to the network. Then we start the first node up with a simple configuration, specifying the node's ID, port, and the location of the AES key file.  
  
To connect another node to we will copy the AES key file to the new machine and run this script.

**Note:** Each node ID is tied to a specific https key signature so every ID on the network must be unique.

```python
from distributed_state_network import DSNodeServer, DSNodeConfig

connector = DSNodeServer(DSNodeConfig(
    node_id="connector", # New node ID
    port=8000, # Port to host the new server on
    aes_key_file= "test.key", # Key file that was copied from first machine
    bootstrap_nodes= [
        {
            # IP address of bootstrap node
            "address": "192.168.0.1",
            "port": 8000
        }
    ]
))
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
The package uses AES, ECDSA, and HTTPS encryption together to protect against network attacks. Each network will have an AES key that authenticates them with the network. Any data traveling between nodes will be encrypted with that key. In addition to this, HTTPS encryption is also used to ensure that nodes send data to the correct destinations. When an authenticated node sends a request to another node, it verifies that the request was sent to the proper place by authenticating the request with a https public key that was previously shared. To make sure that any data that we receive is from a specific node id we use ECDSA encryption to sign state packets.

# Bootstrap Process
The following guide outlines the bootstrap process that is done for every node connecting to the network.

### Hello Packet
For every node connecting to the network we first check if there is a bootstrap node supplied to the configuration. If there is, then we send a Hello Packet to that node. Hello packets allow two nodes to exchange public key data with each other. Say we have a scenario where node A is trying to bootstrap with node B. First, Node A sends a hello packet to node B through a non verified HTTPS request (non verified in that we do not check any https certificates). Before sending the packet, node A encrypts the packet with the network AES key. The schema of the hello packet is outlined below:

```
version: (string) the current protocol version so that we know that the server will respond predictably
node_id: (string) the node ID for the node sending the packet
connection: (Dict) ip address and port data
https_certificate: (bytes) the https public key for the node sending the packet
ecdsa_public_key: (bytes) the ecdsa public key for the node sending the packet
ecdsa_signature: (bytes) the signature of this packets data signed using the sending node's private key
```

Once node B receives the hello packet from node A it attempts to decrypt the packet using its aes key. If it fails then the authentication stops, but if it succeeds then it moves on to the next authenticaion step. Node B then checks if the public key supplied by the packet will verify the packet's ecdsa signature. The version information is also checked to determine if the protocols versions match each other. After all these security checks node B saves node A's https certificate and ecdsa public keys for later use. The authentication will fail if a node tries to connect to the network with a previously known node ID but a different ecdsa or https key. Node B responds to the hello request with the same packet schema that it received. 

## Peers request
Now that nodes A and B have each others public keys they can securely communicate to each other Node B can send a peers request to node A. This request will just return a dictionary of connections with each key relating to a node on the network and the values of the dictionary being their respective IP addresses and corresponding communication ports. Once node A retrieves this info from node B it sends hello packets to every node on the network to authenticate with them and let them know of node A's existence.

## State Update
After each hello packet in the bootstrap process we send a state update request that contains our startup state to the same node. This update request will return the current state of the node being requested. We use this returned data to set the current state for the requested node on node B. The schema for the state update packet is outlined below, this is exactly the same as the data that we store for that node:

```
node_id: (string) node ID of the sending node
ecdsa_signature: (bytes) the signature of the data for the packet signed by the sending node
state_data: (Dictionary) the node's current state
last_update: (DateTime) the time the node was last updated
```

The ecsda signature is important so that we always know that a specific node id has a specific state. State informatin will never come from anywhere but the sending node and every update must be signed with its key.