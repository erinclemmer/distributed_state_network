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
The package uses AES, ECDSA, and HTTPS encryption together to protect against network attacks. Each network will have an AES key that authenticates them with the network. Any data traveling between nodes will be encrypted with that key. In addition to this, HTTPS encryption is also used to ensure that nodes send data to the correct destinations. When an authenticated node sends a request to another node, it verifies that the request was sent to the proper place by authenticating the request with a public key that was previously shared. To make sure that any state data that we receive is from a specific node id we use ECDSA encryption to sign state packets.

# Bootstrap Process
The following guide outlines the bootstrap process that is done for every node connecting to the network.

### Hello Packet
For every node connecting to the network we first check if there is a bootstrap node supplied to the configuration. If there is, then we send a Hello Packet to that node. Hello packets allow two nodes to exchange public key data with each other. Say we have a scenario where node B is trying to bootstrap with node A. First, Node B sends a hello packet to node A through a non verified HTTPS request (non verified in that we do not check any https certificates). Before sending the packet, node B encrypts the packet with the network AES key. The schema of the hello packet is outlined below:

```
version: (string) the current protocol version so that we know that the server will respond predictably
node_id: (string) the node ID for the node sending the packet
connection: (Dict) ip address and port data
https_certificate: (bytes) the https public key for the node sending the packet
ecdsa_public_key: (bytes) the ecdsa public key for the node sending the packet
```

Once node A receives the hello packet from node B it attempts to decrypt the packet using its aes key. If it fails then the authentication stops, but if it succeeds then node A saves node B's https certificate and ecdsa public keys for later use. The authentication will fail if a node tries to connect to the network with a previously known node ID but a different key. Node A responds to the hello request with the same packet schema that it received. 

## Peers request
Now that nodes A and B have each others public keys they can securely communicate to each other. Once that happens node B can send a peers request to node A. This request will just return a dictionary of connections with each key relating to a node on the network and the values being their respective IP addresses and corresponding ports. Once node B retrieves this info from node A it sends hello packets to every node on the network to authenticate with them and let them know of node B's existence.

## State Update
After each hello packet in the bootstrap process we send a state update request that contains our startup state to the same node. This update request will return the current state of the node being requested. We use this returned data to set the current state for the requested node on node B. The schema for the state update packet is outlined below, this is exactly the same as the data that we store for that node:

```
node_id: (string) node ID of the sending node
connection: (Dictionary) ip address and port informationo fo rthe 
```

The `state_data` portion of the packet will contain the state information for all nodes in the network so that node B will have an updated view of the current network. Through this information it will also know the connection information to all the nodes in the network, but it needs to know the https certificates of each node in order to and ecdsa communicate withs
### Hello Packet
Once node B is authenticated with node A then it finds out about the existence of node C in the network through the `state_data` information. To be sure that we will always send data to the correct server we need to request the https certificate public key of node C. We do this with a hello packet. The schema for the hello packet is outlined below:

```
node_id: (string) the node ID for the node sending the packet
https_certificate: (bytes) the https certificate for the node sending the packett
```

This is just a stripped down version of the bootstrap packet because we already know that node C is on the same version as node A since the authentication went through correctly. And we already know the state data for node C because 