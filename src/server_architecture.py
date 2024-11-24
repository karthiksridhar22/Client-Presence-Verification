import socket
import threading
import time


class Server:
    def __init__(self, host, port, peers=None, identifier=None):
        """
        Initializes a Server object to act as a node in a P2P network and handle client connections.

        :param host: The IP address of the server.
        :param port: The port on which the server listens.
        :param peers: Dictionary of peer identifiers mapped to their (host, port) tuples.
        :param identifier: Unique identifier for the server.
        """
        self.host = host
        self.port = port
        self.identifier = identifier  # Unique identifier for this server
        self.peers = peers or {}  # Mapping of peer identifiers to (host, port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connections = {}  # Map identifiers to connections with peers
        self.client_connections = {}  # Map identifiers to connections with clients
        self.running = True
        self.lock = threading.Lock()
        self.delays_file = "delays.txt"  # File to log delay measurements

    def start(self):
        """
        Starts the server by launching threads for listening to connections and handling commands.
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
        Handles an incoming connection from a peer or client.

        :param connection: The socket object for the connection.
        :param address: The address of the incoming connection.
        """
        try:
            data = connection.recv(1024).decode()
            if data.startswith("HELLO"):
                identifier = data.split(" ")[1]
                if identifier.startswith("client"):
                    with self.lock:
                        self.client_connections[identifier] = connection
                    print(f"[{self.identifier}] Incoming connection from client {identifier} ({address})")
                    threading.Thread(
                        target=self._handle_client, args=(connection, identifier), daemon=True
                    ).start()
                else:
                    with self.lock:
                        self.connections[identifier] = {"incoming": connection, "outgoing": None}
                    print(f"[{self.identifier}] Incoming connection from {identifier} ({address})")
                    threading.Thread(
                        target=self._handle_peer, args=(connection, identifier), daemon=True
                    ).start()
            else:
                print(f"[{self.identifier}] Unexpected data from {address}: {data}")
        except socket.error as e:
            print(f"[{self.identifier}] Error handling incoming connection from {address}: {e}")

    def _handle_client(self, connection, identifier):
        """
        Handles communication with a client, including responding to delay measurement requests.

        :param connection: The socket object for the client.
        :param identifier: The unique identifier of the client.
        """
        try:
            while self.running:
                data = connection.recv(1024).decode()
                if not data:
                    continue
                print(f"[{self.identifier}] Received from client {identifier}: {data}")
                if data == "MEASURE_DELAYS_REQUEST":
                    t2 = time.time()
                    connection.sendall(f"MEASURE_DELAYS_RESPONSE {t2}".encode())
        except socket.error as e:
            print(f"[{self.identifier}] Connection error with client {identifier}: {e}")
        finally:
            with self.lock:
                connection.close()
                self.client_connections.pop(identifier, None)
                print(f"[{self.identifier}] Disconnected from client {identifier}")

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
        if identifier in self.connections and self.connections[identifier].get("outgoing"):
            print(f"[{self.identifier}] Already connected to {identifier} (outgoing). Skipping.")
            return

        try:
            outgoing_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            outgoing_socket.connect((peer_host, peer_port))
            outgoing_socket.sendall(f"HELLO {self.identifier}".encode())
            with self.lock:
                if identifier not in self.connections:
                    self.connections[identifier] = {"incoming": None, "outgoing": outgoing_socket}
                else:
                    self.connections[identifier]["outgoing"] = outgoing_socket

            print(f"[{self.identifier}] Outgoing connection to {identifier} ({peer_host}:{peer_port})")
            threading.Thread(
                target=self._handle_peer, args=(outgoing_socket, identifier), daemon=True
            ).start()
        except socket.error as e:
            print(f"[{self.identifier}] Failed to connect to {identifier}: {e}")

    def _handle_peer(self, connection, identifier):
        """
        Handles communication with a peer, including delay measurements.

        :param connection: The socket object for the peer.
        :param identifier: The unique identifier of the peer.
        """
        try:
            while self.running:
                data = connection.recv(1024).decode()
                if not data:
                    continue

                print(f"[{self.identifier}] Received from {identifier}: {data}")
                if data == "MEASURE_DELAYS_REQUEST":
                    t2 = time.time()
                    connection.sendall(f"MEASURE_DELAYS_RESPONSE {t2}".encode())
                elif data.startswith("MEASURE_DELAYS_RESPONSE"):
                    _, t2 = data.split(" ")
                    t3 = time.time()
                    delay = (t3 - float(t2)) / 2
                    self._log_delay(self.identifier, identifier, delay)
        except socket.error as e:
            print(f"[{self.identifier}] Connection error with {identifier}: {e}")
        finally:
            with self.lock:
                connection.close()
                if identifier in self.connections:
                    self.connections.pop(identifier, None)
                print(f"[{self.identifier}] Disconnected from peer {identifier}")

    def measure_delays(self):
        """
        Initiates a delay measurement protocol with all connected peers and clients.

        Sends a 'MEASURE_DELAYS_REQUEST' to all connected peers and clients.
        """
        with self.lock:
            # Measure delays with peers
            for identifier, sockets in self.connections.items():
                outgoing_socket = sockets.get("outgoing")
                if outgoing_socket:
                    try:
                        outgoing_socket.sendall("MEASURE_DELAYS_REQUEST".encode())
                    except socket.error as e:
                        print(f"[{self.identifier}] Failed to initiate delay measurement with {identifier}: {e}")
            
            # Measure delays with clients
            for client_id, connection in self.client_connections.items():
                try:
                    connection.sendall("MEASURE_DELAYS_REQUEST".encode())
                except socket.error as e:
                    print(f"[{self.identifier}] Failed to initiate delay measurement with client {client_id}: {e}")

    def _log_delay(self, from_id, to_id, delay):
        """
        Logs the measured delay to the delays file.

        :param from_id: Identifier of the sender.
        :param to_id: Identifier of the receiver.
        :param delay: The measured delay in seconds.
        """
        print(f"[{self.identifier}] Measured delay between {from_id} and {to_id}: {delay:.6f} seconds")
        with open(self.delays_file, "a") as file:
            file.write(f"{from_id},{to_id},{delay:.6f}\n")

    def list_connections(self):
        """
        Lists all active connections to peers and clients.
        """
        with self.lock:
            print(f"[{self.identifier}] Connections:")
            for identifier, sockets in self.connections.items():
                if sockets.get("incoming") or sockets.get("outgoing"):
                    print(f"  - Peer: {identifier}")
            for client_id in self.client_connections.keys():
                print(f"  - Client: {client_id}")

    def shutdown(self):
        """
        Gracefully shuts down the server, closing all connections and notifying peers.
        """
        print(f"[{self.identifier}] Shutting down...")
        self.running = False
        with self.lock:
            for identifier, sockets in list(self.connections.items()):
                for conn_type, conn in sockets.items():
                    if conn:
                        conn.close()
                self.connections.pop(identifier, None)
            for client_id, connection in list(self.client_connections.items()):
                connection.close()
                self.client_connections.pop(client_id, None)
            self.socket.close()
    
    def command_loop(self):
        """
        Provides a command-line interface for the user to interact with the server.
        """
        while self.running:
            command = input("Enter command (list/send/connect/measure_delays/close): ").strip().lower()
            if command == "list":
                self.list_connections()
            elif command.startswith("send "):
                _, message = command.split(" ", 1)
                self.send_data(message)
            elif command == "connect":
                self.connect_to_peers()
            elif command == "measure_delays":
                self.measure_delays()
            elif command == "close":
                self.shutdown()
                break
            else:
                print("Available commands: list, send <message>, connect, measure_delays, close")
