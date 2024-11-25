import socket
import threading
import time


class Client:
    def __init__(self, identifier, servers):
        """
        Initializes the Client object to connect to multiple servers.

        :param identifier: Unique identifier for the client.
        :param servers: Dictionary of server identifiers mapped to their (host, port) tuples.
        """
        self.identifier = identifier  # Unique identifier for this client
        self.servers = servers  # Mapping of server identifiers to (host, port)
        self.connections = {}  # Map server identifiers to their socket connections
        self.running = True
        self.lock = threading.Lock()

    def start(self):
        """
        Starts the client by launching the command loop.
        """
        threading.Thread(target=self.command_loop, daemon=True).start()

    def connect_to_servers(self):
        """
        Connects to all predefined servers.
        """
        for identifier, (server_host, server_port) in self.servers.items():
            self.connect(identifier, server_host, server_port)

    def connect(self, identifier, server_host, server_port):
        """
        Establishes an outgoing connection to a server.
        """
        if identifier in self.connections:
            print(f"[{self.identifier}] Already connected to {identifier}. Skipping.")
            return

        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.connect((server_host, server_port))
            server_socket.sendall(f"HELLO {self.identifier}".encode())
            with self.lock:
                self.connections[identifier] = server_socket
            threading.Thread(
                target=self._handle_server, args=(server_socket, identifier), daemon=True
            ).start()
            print(f"[{self.identifier}] Connected to server {identifier} ({server_host}:{server_port})")
        except socket.error as e:
            print(f"[{self.identifier}] Failed to connect to {identifier}: {e}")

    def _handle_server(self, connection, identifier):
        """
        Handles communication with a server.
        """
        try:
            while self.running:
                data = connection.recv(1024).decode()
                if not data:
                    continue
                if data.startswith("OWD_MEASUREMENT_REQUEST"):
                    # Respond immediately with current time
                    response_time = time.time()
                    message = f"OWD_MEASUREMENT_RESPONSE {self.identifier} {response_time}"
                    connection.sendall(message.encode())
                else:
                    print(f"[{self.identifier}] Received from {identifier}: {data}")
        except socket.error as e:
            print(f"[{self.identifier}] Connection error with {identifier}: {e}")
        finally:
            with self.lock:
                connection.close()
                self.connections.pop(identifier, None)
                print(f"[{self.identifier}] Disconnected from {identifier}")

    def list_connections(self):
        """
        Lists all active connections to servers.
        """
        with self.lock:
            print(f"[{self.identifier}] Connected servers:")
            for identifier in self.connections.keys():
                print(f"  - {identifier}")

    def shutdown(self):
        """
        Gracefully shuts down the client, closing all connections.
        """
        print(f"[{self.identifier}] Shutting down...")
        self.running = False
        with self.lock:
            for identifier, connection in self.connections.items():
                try:
                    connection.close()
                    print(f"[{self.identifier}] Closed connection with {identifier}")
                except (socket.error, OSError):
                    pass
            self.connections.clear()

    def command_loop(self):
        """
        Provides a command-line interface for the user to interact with the client.
        """
        while self.running:
            command = input("Enter command (list/connect/close): ").strip().lower()
            if command == "list":
                self.list_connections()
            elif command == "connect":
                self.connect_to_servers()
            elif command == "close":
                self.shutdown()
                break
            else:
                print("Available commands: list, connect, close")
