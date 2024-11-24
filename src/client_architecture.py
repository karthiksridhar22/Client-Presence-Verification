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
        self.delays_file = "delays.txt"  # File to log delay measurements

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

        :param identifier: The unique identifier of the server.
        :param server_host: The host of the server.
        :param server_port: The port of the server.
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

        :param connection: The socket object for the server.
        :param identifier: The unique identifier of the server.
        """
        try:
            while self.running:
                data = connection.recv(1024).decode()
                if not data:
                    continue
                print(f"[{self.identifier}] Received from {identifier}: {data}")
                if data.startswith("MEASURE_DELAYS_RESPONSE"):
                    self._handle_measure_delays(connection, identifier, data)
        except socket.error as e:
            print(f"[{self.identifier}] Connection error with {identifier}: {e}")
        finally:
            with self.lock:
                connection.close()
                self.connections.pop(identifier, None)
                print(f"[{self.identifier}] Disconnected from {identifier}")

    def measure_delays(self):
      """
      Initiates a delay measurement protocol with all connected servers.
      Logs delays for client-to-server communication.
      """
      with self.lock:
          for identifier, connection in self.connections.items():
              try:
                  # Send delay measurement request to each server
                  connection.sendall("MEASURE_DELAYS_REQUEST".encode())
              except socket.error as e:
                  print(f"[{self.identifier}] Failed to initiate delay measurement with {identifier}: {e}")

    def _handle_measure_delays(self, connection, identifier, data):
        """
        Handles the MEASURE_DELAYS_RESPONSE from servers and logs delay.

        :param connection: The socket object for the server.
        :param identifier: The unique identifier of the server.
        :param data: The data received from the server.
        """
        if data.startswith("MEASURE_DELAYS_RESPONSE"):
            _, t2 = data.split(" ")
            t3 = time.time()
            delay = (t3 - float(t2)) / 2
            print(f"[{self.identifier}] Measured delay with {identifier}: {delay:.6f} seconds")
            with open(self.delays_file, "a") as file:
                file.write(f"{self.identifier},{identifier},{delay:.6f}\n")

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
            command = input("Enter command (list/connect/measure_delays/close): ").strip().lower()
            if command == "list":
                self.list_connections()
            elif command.startswith("connect"):
                self.connect_to_servers()
            elif command == "measure_delays":
                self.measure_delays()
            elif command == "close":
                self.shutdown()
                break
            else:
                print("Available commands: list, connect, measure_delays, close")
