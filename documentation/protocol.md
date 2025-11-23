## Network Protocol

### Transport Layer
The network now uses **UDP (User Datagram Protocol)** for all communication instead of HTTP/HTTPS. This provides:
- Lower latency for peer-to-peer communication
- Reduced overhead compared to HTTP
- Simpler connection management
- More suitable for real-time distributed systems

### Message Types
All UDP packets use a message type byte prefix to identify the packet type:

- **Type 1 (HELLO)**: Exchange node information and credentials
- **Type 2 (PEERS)**: Request/share peer list
- **Type 3 (UPDATE)**: Send/receive state updates
- **Type 4 (PING)**: Connectivity check

### Packet Structure
Each UDP packet follows this structure:
1. **AES Encrypted Payload** containing:
   - Message type (1 byte)
   - Message payload (variable length)

### Security
- All communication is encrypted using AES with a shared key
- Messages are signed using ECDSA for authentication
- UDP packets are encrypted end-to-end
- HTTPS/TLS is not supported with UDP (certificates are no longer used)

### State Synchronization
- Nodes maintain a copy of all peers' states
- Updates are broadcast to all connected peers
- Timestamps prevent older updates from overwriting newer ones

### Socket Management
- You can provide a custom UDP socket when starting a server
- If no socket is provided, one will be created and bound automatically
- Socket timeout is set to 2 seconds for requests
- Maximum UDP packet size is 65507 bytes

## Important Notes

1. **Shared AES Key**: All nodes in the network must use the same AES key file
2. **Unique Node IDs**: Each node must have a unique node_id
3. **Port Availability**: Ensure the specified UDP port is available before starting
4. **Bootstrap Nodes**: At least one bootstrap node is required to join an existing network
5. **Network Tick**: The network performs maintenance checks every 3 seconds
6. **Credential Management**: ECDSA keys are automatically generated and stored in `credentials/` directory
7. **UDP Reliability**: The protocol implements retry logic (up to 3 attempts) for failed requests
8. **HTTPS Not Supported**: The `https` configuration option is ignored when using UDP

## Error Handling

Common error codes (embedded in exception messages):
- **401**: Not Authorized (signature verification failed)
- **406**: Not Acceptable (invalid data, stale update, or version mismatch)
- **505**: Version not supported

## Migration from HTTP

If you're migrating from the HTTP-based version:
1. Remove any HTTPS certificate dependencies
2. Update firewall rules to allow UDP traffic on your ports
3. The API remains largely the same, but transport is now UDP
4. The `https` flag in configuration is now ignored
