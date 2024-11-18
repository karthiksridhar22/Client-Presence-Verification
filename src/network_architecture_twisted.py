from twisted.internet import reactor, protocol
from twisted.protocols.basic import LineReceiver

class NodeProtocol(LineReceiver):
    """
    Protocol for handling connections between nodes.
    """
    def __init__(self, factory):
        self.factory = factory

    def connectionMade(self):
        peer = self.transport.getPeer()
        print(f"Connected to {peer.host}:{peer.port}")
        self.factory.connections.append(self)

    def connectionLost(self, reason):
        print("Connection lost.")
        self.factory.connections.remove(self)

    def lineReceived(self, line):
        print(f"Received: {line.decode('utf-8')}")
        # Optionally broadcast received messages to all connected nodes
        for conn in self.factory.connections:
            if conn != self:
                conn.sendLine(line)

    def sendLineToPeer(self, message):
        self.sendLine(message.encode('utf-8'))


class NodeFactory(protocol.ServerFactory):
    """
    Factory for managing node connections.
    """
    protocol = NodeProtocol

    def __init__(self):
        self.connections = []  # Active connections


class NodeClientProtocol(LineReceiver):
    """
    Protocol for handling outgoing connections.
    """
    def __init__(self, factory):
        self.factory = factory

    def connectionMade(self):
        print("Successfully connected to peer!")
        self.factory.client_ready(self)

    def lineReceived(self, line):
        print(f"Received from peer: {line.decode('utf-8')}")


class NodeClientFactory(protocol.ClientFactory):
    """
    Factory for managing outgoing client connections.
    """
    protocol = NodeClientProtocol

    def __init__(self):
        self.protocol_instance = None

    def client_ready(self, protocol_instance):
        self.protocol_instance = protocol_instance

    def send_message(self, message):
        if self.protocol_instance:
            self.protocol_instance.sendLine(message.encode('utf-8'))
        else:
            print("Client not connected yet.")

    def clientConnectionFailed(self, connector, reason):
        print(f"Connection failed: {reason}")
        reactor.stop()

    def clientConnectionLost(self, connector, reason):
        print(f"Connection lost: {reason}")
        reactor.stop()


def start_server(host, port):
    """
    Start a Twisted server node.
    """
    factory = NodeFactory()
    reactor.listenTCP(port, factory)
    print(f"Server listening on {host}:{port}")
    return factory


def connect_to_peer(host, port):
    """
    Connect to a peer node as a client.
    """
    factory = NodeClientFactory()
    reactor.connectTCP(host, port, factory)
    return factory


def main():
    """
    Initialize the network nodes.
    """
    import sys
    if len(sys.argv) != 3:
        print("Usage: python twisted_node.py <host> <port>")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])

    # Start server
    server_factory = start_server(host, port)

    # Example peer connections (you can customize this)
    if port == 5110:
        connect_to_peer('127.0.0.1', 5111)
        connect_to_peer('127.0.0.1', 5112)
    elif port == 5011:
        connect_to_peer('127.0.0.1', 5110)
        connect_to_peer('127.0.0.1', 5112)
    elif port == 5012:
        connect_to_peer('127.0.0.1', 5110)
        connect_to_peer('127.0.0.1', 5111)

    # Run the reactor
    reactor.run()


if __name__ == "__main__":
    main()
