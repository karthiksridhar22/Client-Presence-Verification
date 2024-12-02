# client_architecture.py

import socket
import threading
import time
from . import cpv_utils
import logging

logger = logging.getLogger(__name__)

class Client:
    def __init__(self, identifier, servers):
        """
        Initializes the Client object to connect to multiple servers.

        Args:
            identifier (str): Unique identifier for this client.
            servers (dict): Mapping of server identifiers to (host, port).
        """
        self.identifier = identifier  # Unique identifier for this client
        self.servers = servers  # Mapping of server identifiers to (host, port)
        self.connections = {}  # Map server identifiers to their socket connections
        self.running = True
        self.lock = threading.Lock()
        self.session_id = None  # Session ID for the current measurement
        self.forwarded_timestamps = set()  # To prevent redundant forwarding

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
            logger.info(f"[{self.identifier}] Already connected to {identifier}. Skipping.")
            return

        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.connect((server_host, server_port))
            message = cpv_utils.construct_message(cpv_utils.HELLO, self.identifier)
            server_socket.sendall(message.encode())
            with self.lock:
                self.connections[identifier] = server_socket
            threading.Thread(
                target=self._handle_server, args=(server_socket, identifier), daemon=True
            ).start()
            logger.info(f"[{self.identifier}] Connected to server {identifier} ({server_host}:{server_port})")
        except socket.error as e:
            logger.error(f"[{self.identifier}] Failed to connect to {identifier}: {e}")

    def _handle_server(self, connection, identifier):
        """
        Handles communication with a server.
        """
        try:
            while self.running:
                data = connection.recv(1024).decode()
                if not data:
                    continue
                message_type, params = cpv_utils.parse_message(data)
                if message_type == cpv_utils.TIMESTAMP:
                    # Verifier sent timestamp; forward to all verifiers
                    sender_id = params[0]
                    timestamp = params[1]
                    iteration = params[2]
                    self._forward_timestamp_to_verifiers(sender_id, timestamp, iteration)
                elif message_type == cpv_utils.START_MEASUREMENTS:
                    # Start measurements
                    session_id = params[0]
                    iterations = int(params[1])
                    self.session_id = session_id
                    logger.info(f"[{self.identifier}] Starting measurements for session {session_id}")
                    # No action needed; verifiers initiate measurements
                else:
                    logger.info(f"[{self.identifier}] Received from {identifier}: {data}")
        except socket.error as e:
            logger.error(f"[{self.identifier}] Connection error with {identifier}: {e}")
        finally:
            with self.lock:
                connection.close()
                self.connections.pop(identifier, None)
                logger.info(f"[{self.identifier}] Disconnected from {identifier}")

    def _forward_timestamp_to_verifiers(self, sender_id, timestamp, iteration):
        """
        Forwards a timestamp received from one verifier to all verifiers.
        """
        key = (sender_id, timestamp, iteration)
        with self.lock:
            if key in self.forwarded_timestamps:
                return  # Already forwarded this timestamp
            self.forwarded_timestamps.add(key)

        message = cpv_utils.construct_message(
            cpv_utils.FORWARD_TIMESTAMP, sender_id, timestamp, iteration
        )
        with self.lock:
            for identifier, connection in self.connections.items():
                if identifier != sender_id:
                    try:
                        connection.sendall(message.encode())
                        logger.info(f"[{self.identifier}] Forwarded timestamp from {sender_id} to {identifier}")
                    except socket.error as e:
                        logger.error(f"[{self.identifier}] Error forwarding timestamp to {identifier}: {e}")

    def list_connections(self):
        """
        Lists all active connections to servers.
        """
        with self.lock:
            logger.info(f"[{self.identifier}] Connected servers:")
            for identifier in self.connections.keys():
                logger.info(f"  - {identifier}")

    def shutdown(self):
        """
        Gracefully shuts down the client, closing all connections.
        """
        logger.info(f"[{self.identifier}] Shutting down...")
        self.running = False
        with self.lock:
            for identifier, connection in self.connections.items():
                try:
                    connection.close()
                    logger.info(f"[{self.identifier}] Closed connection with {identifier}")
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
                logger.info("Available commands: list, connect, close")
