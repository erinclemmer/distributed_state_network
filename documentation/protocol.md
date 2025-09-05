## Network Protocol

### Endpoints
The server exposes the following HTTPS endpoints:

- **POST /hello**: Exchange node information and certificates
- **POST /peers**: Request/share peer list
- **POST /update**: Send/receive state updates
- **POST /ping**: Connectivity check

### Security
- All communication is encrypted using AES with a shared key
- Messages are signed using ECDSA for authentication
- HTTPS with self-signed certificates for transport security

### State Synchronization
- Nodes maintain a copy of all peers' states
- Updates are broadcast to all connected peers
- Timestamps prevent older updates from overwriting newer ones

## Important Notes

1. **Shared AES Key**: All nodes in the network must use the same AES key file
2. **Unique Node IDs**: Each node must have a unique node_id
3. **Port Availability**: Ensure the specified port is available before starting
4. **Bootstrap Nodes**: At least one bootstrap node is required to join an existing network
5. **Network Tick**: The network performs maintenance checks every 3 seconds
6. **Certificate Management**: Certificates and keys are automatically generated and stored in `certs/` and `credentials/` directories

## Error Handling

Common HTTP status codes returned:
- **200**: Success
- **401**: Not Authorized (signature verification failed)
- **404**: Endpoint not found
- **406**: Not Acceptable (invalid data or version mismatch)
- **505**: Version not supported
