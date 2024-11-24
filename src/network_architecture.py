import socket
import threading


class Node:
    def __init__(self, host, port, peers=None, identifier=None):
        """
        Initializes a Node object to act as a server and client in a P2P network.

        :param host: The IP address of the node.
        :param port: The port on which the node listens.
        :param peers: Dictionary of peer identifiers mapped to their (host, port) tuples.
        :param identifier: Unique identifier for the node.
        """
        self.host = host
        self.port = port
        self.identifier = identifier  # Unique identifier for this server
        self.peers = peers or {}  # Mapping of identifiers to (host, port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connections = {}  # Map identifiers to both incoming and outgoing sockets
        self.running = True
        self.lock = threading.Lock()

    def start(self):
        """
        Starts the node by launching threads for listening to connections and handling commands.
        """
        threading.Thread(target=self.listen, daemon=True).start()
        threading.Thread(target=self.command_loop, daemon=True).start()

    def listen(self):
        """
        Listens for incoming connections and spawns threads to handle each one.
        """
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)
        print(f"[{self.identifier}] Listening on {self.host}:{self.port}")
        while self.running:
            try:
                connection, address = self.socket.accept()
                threading.Thread(
                    target=self._handle_incoming_connection, args=(connection, address), daemon=True
                ).start()
            except socket.error as e:
                if self.running:
                    print(f"[{self.identifier}] Error accepting connection: {e}")

    def _handle_incoming_connection(self, connection, address):
        """
        Handles an incoming connection, establishing it as part of the P2P network.

        :param connection: The socket object for the connection.
        :param address: The address of the incoming connection.
        """
        try:
            data = connection.recv(1024).decode()
            if data.startswith("HELLO"):
                identifier = data.split(" ")[1]
                with self.lock:
                    if identifier not in self.connections:
                        self.connections[identifier] = {"incoming": connection, "outgoing": None}
                        print(f"[{self.identifier}] Incoming connection from {identifier} ({address})")
                    else:
                        self.connections[identifier]["incoming"] = connection
                threading.Thread(
                    target=self._handle_peer, args=(connection, identifier), daemon=True
                ).start()
            else:
                print(f"[{self.identifier}] Unexpected data from {address}: {data}")
        except socket.error as e:
            print(f"[{self.identifier}] Error handling incoming connection from {address}: {e}")

    def connect_to_peers(self):
        """
        Connects to all predefined peers in the P2P network.
        """
        for identifier, (peer_host, peer_port) in self.peers.items():
            self.connect(identifier, peer_host, peer_port)

    def connect(self, identifier, peer_host, peer_port):
        """
        Establishes an outgoing connection to a peer.

        :param identifier: The unique identifier of the peer.
        :param peer_host: The host of the peer.
        :param peer_port: The port of the peer.
        """
        if identifier in self.connections and self.connections[identifier]["outgoing"]:
            print(f"[{self.identifier}] Already connected to {identifier} (outgoing). Skipping.")
            return

        try:
            outgoing_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            outgoing_socket.connect((peer_host, peer_port))
            with self.lock:
                if identifier not in self.connections:
                    self.connections[identifier] = {"incoming": None, "outgoing": outgoing_socket}
                else:
                    self.connections[identifier]["outgoing"] = outgoing_socket

            outgoing_socket.sendall(f"HELLO {self.identifier}".encode())
            print(f"[{self.identifier}] Outgoing connection to {identifier} ({peer_host}:{peer_port})")
            threading.Thread(
                target=self._handle_peer, args=(outgoing_socket, identifier), daemon=True
            ).start()
        except socket.error as e:
            print(f"[{self.identifier}] Failed to connect to {identifier}: {e}")

    def _handle_peer(self, connection, identifier):
        """
        Handles communication with a peer, processing messages such as DISCONNECT.

        :param connection: The socket object for the peer.
        :param identifier: The unique identifier of the peer.
        """
        try:
            while self.running:
                data = connection.recv(1024).decode()
                if not data:
                    continue

                print(f"[{self.identifier}] Received from {identifier}: {data}")
                if data == "DISCONNECT":
                    with self.lock:
                        if identifier in self.connections:
                            for conn_type, conn in self.connections[identifier].items():
                                if conn:
                                    conn.close()
                            self.connections.pop(identifier, None)
                            print(f"[{self.identifier}] Removed connection with {identifier} due to DISCONNECT")
                    break
        except socket.error as e:
            print(f"[{self.identifier}] Connection error with {identifier}: {e}")
        finally:
            with self.lock:
                if identifier in self.connections:
                    for conn_type, conn in self.connections[identifier].items():
                        if conn:
                            conn.close()
                    self.connections.pop(identifier, None)
                print(f"[{self.identifier}] Cleaned up connection with {identifier}")

    def list_connections(self):
        """
        Lists all active connections to peers.
        """
        with self.lock:
            print(f"[{self.identifier}] Connections:")
            for identifier, sockets in self.connections.items():
                if sockets["incoming"] or sockets["outgoing"]:
                    print(f"  - {identifier}")

    def send_data(self, message):
        """
        Sends a message to all connected peers.

        :param message: The message to send.
        """
        with self.lock:
            for identifier, sockets in self.connections.items():
                if sockets["outgoing"]:
                    try:
                        sockets["outgoing"].sendall(message.encode())
                    except socket.error as e:
                        print(f"[{self.identifier}] Failed to send to {identifier}: {e}")

    def notify_disconnect(self):
        """
        Notifies all peers about this node shutting down.
        """
        with self.lock:
            for identifier, sockets in self.connections.items():
                for conn_type, conn in sockets.items():
                    if conn:
                        try:
                            conn.sendall("DISCONNECT".encode())
                        except (socket.error, OSError):
                            pass  # Ignore errors during notification

    def shutdown(self):
        """
        Gracefully shuts down the node, closing all connections and notifying peers.
        """
        print(f"[{self.identifier}] Shutting down...")
        self.running = False
        self.notify_disconnect()
        with self.lock:
            for identifier, sockets in list(self.connections.items()):
                for conn_type, conn in sockets.items():
                    if conn:
                        try:
                            conn.close()
                            print(f"[{self.identifier}] Closed {conn_type} connection with {identifier}")
                        except (socket.error, OSError):
                            pass
                self.connections.pop(identifier, None)
        try:
            self.socket.close()
            print(f"[{self.identifier}] Listening socket closed")
        except (socket.error, OSError):
            pass

    def command_loop(self):
        """
        Provides a command-line interface for the user to interact with the node.
        """
        while self.running:
            command = input("Enter command (list/send/connect/close): ").strip().lower()
            if command == "list":
                self.list_connections()
            elif command.startswith("send "):
                _, message = command.split(" ", 1)
                self.send_data(message)
            elif command == "connect":
                self.connect_to_peers()
            elif command == "close":
                self.shutdown()
                break
            else:
                print("Available commands: list, send <message>, connect, close")
