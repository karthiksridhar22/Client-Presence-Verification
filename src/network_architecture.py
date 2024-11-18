import socket
import threading
import time


class Node:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connections = []
        self.peer_addresses = []
        self.running = True
        self.lock = threading.Lock()  # Protect shared resources

    def start(self):
        listen_thread = threading.Thread(target=self.listen, daemon=True)
        listen_thread.start()

        # Command loop
        threading.Thread(target=self.command_loop, daemon=True).start()

    def listen(self):
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)
        print(f"Listening for connections on {self.host}:{self.port}")
        while self.running:
            try:
                connection, address = self.socket.accept()
                with self.lock:
                    self.connections.append(connection)
                    self.peer_addresses.append(address)
                print(f"Accepted connection from {address}")
                threading.Thread(target=self._handle_peer, args=(connection,), daemon=True).start()
            except socket.error as e:
                if self.running:
                    print(f"Error accepting connection: {e}")

    def connect(self, peer_host, peer_port, max_retries=5):
        retries = 0
        while retries < max_retries:
            try:
                outgoing_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                outgoing_socket.connect((peer_host, peer_port))
                with self.lock:
                    self.connections.append(outgoing_socket)
                    self.peer_addresses.append((peer_host, peer_port))
                print(f"Connected to {peer_host}:{peer_port}")
                threading.Thread(target=self._handle_peer, args=(outgoing_socket,), daemon=True).start()
                return
            except socket.error as e:
                retries += 1
                print(f"Failed to connect to {peer_host}:{peer_port}. Retrying {retries}/{max_retries}... Error: {e}")
                time.sleep(2)
        print(f"Failed to connect to {peer_host}:{peer_port} after {max_retries} retries.")

    def _handle_peer(self, connection):
        while self.running:
            try:
                data = connection.recv(1024).decode()
                if data:
                    print(f"Received data: {data}")
                else:
                    # Ignore empty data; do not remove connection unless explicitly closed
                    continue
            except socket.error as e:
                print(f"Connection error: {e}")
                break

    def send_data(self, data):
        with self.lock:
            for connection in self.connections:
                try:
                    connection.sendall(data.encode())
                except socket.error as e:
                    print(f"Failed to send data: {e}")

    def list_connections(self):
        with self.lock:
            for address in self.peer_addresses:
                print(f"Connected to: {address}")

    def shutdown(self):
        print("Shutting down the server...")
        self.running = False
        with self.lock:
            for connection in self.connections:
                connection.close()
        self.socket.close()

    def command_loop(self):
        while self.running:
            command = input("Enter command (list/close): ").strip().lower()
            if command == "list":
                self.list_connections()
            elif command == "close":
                self.shutdown()
                break
            else:
                print("Unknown command. Available commands: list, close.")
