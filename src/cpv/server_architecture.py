# server_architecture.py

import socket
import threading
import time
import uuid
from . import cpv_utils
import json
import logging

logger = logging.getLogger(__name__)

class Server:
    def __init__(self, host, port, peers=None, identifier=None):
        """
        Initializes a Server object to act as a verifier in the CPV protocol.

        Args:
            host (str): The hostname or IP address to bind the server.
            port (int): The port number to bind the server.
            peers (dict, optional): A mapping of peer identifiers to (host, port).
            identifier (str, optional): A unique identifier for this server.
        """
        self.host = host
        self.port = port
        self.identifier = identifier  # Unique identifier for this server (e.g., 'server1')
        self.peers = peers or {}  # Mapping of peer identifiers to (host, port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connections = {}  # Map identifiers to connections with peers
        self.client_connections = {}  # Map identifiers to connections with clients
        self.running = True
        self.lock = threading.Lock()
        self.session_id = None  # Shared session ID for each measurement instance

        # Data structures for protocols
        self.dic_dcj_sums = {}  # Stores dic + dcj sums for mp protocol
        self.min_sums = {}  # Stores min(dic + dcj, djc + dci) for mp protocol
        self.av_delays = {}     # Stores delays from av protocol

        self.delays_mp_file = "delays_mp.json"  # File to log mp delays
        self.delays_av_file = "delays_av.json"  # File to log av delays

        # Clear delay files on startup
        open(self.delays_mp_file, 'w').close()
        open(self.delays_av_file, 'w').close()

        # Measurements storage
        self.verifier_measurements = {}  # For av protocol
        self.forwarded_timestamps = set()  # To prevent redundant forwarding

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
        logger.info(f"[{self.identifier}] Listening on {self.host}:{self.port}")
        while self.running:
            try:
                connection, address = self.socket.accept()
                threading.Thread(
                    target=self._handle_incoming_connection, args=(connection, address), daemon=True
                ).start()
            except socket.error as e:
                if self.running:
                    logger.error(f"[{self.identifier}] Error accepting connection: {e}")

    def _handle_incoming_connection(self, connection, address):
        """
        Handles an incoming connection from a peer or client.
        """
        try:
            data = connection.recv(1024).decode()
            if data.startswith(cpv_utils.HELLO):
                _, identifier = data.strip().split()
                if identifier.startswith("client"):
                    with self.lock:
                        self.client_connections[identifier] = connection
                    logger.info(f"[{self.identifier}] Incoming connection from client {identifier} ({address})")
                    threading.Thread(
                        target=self._handle_client, args=(connection, identifier), daemon=True
                    ).start()
                else:
                    with self.lock:
                        if identifier not in self.connections:
                            self.connections[identifier] = {"incoming": connection, "outgoing": None}
                        else:
                            self.connections[identifier]["incoming"] = connection
                    logger.info(f"[{self.identifier}] Incoming connection from {identifier} ({address})")
                    threading.Thread(
                        target=self._handle_peer, args=(connection, identifier), daemon=True
                    ).start()
            else:
                logger.warning(f"[{self.identifier}] Unexpected data from {address}: {data}")
        except socket.error as e:
            logger.error(f"[{self.identifier}] Error handling incoming connection from {address}: {e}")

    def _handle_client(self, connection, identifier):
        """
        Handles communication with a client.
        """
        try:
            while self.running:
                data = connection.recv(1024).decode()
                if not data:
                    continue
                message_type, params = cpv_utils.parse_message(data)
                if message_type == cpv_utils.FORWARD_TIMESTAMP:
                    # Handle forwarded timestamp from client
                    sender_id = params[0]
                    timestamp = float(params[1])
                    iteration = int(params[2])
                    self._handle_timestamp_from_client(sender_id, timestamp, iteration)
                elif message_type == cpv_utils.START_MEASUREMENTS:
                    session_id = params[0]
                    iterations = int(params[1])
                    self.session_id = session_id
                    self.measure_delays(iterations)
                else:
                    logger.info(f"[{self.identifier}] Received from client {identifier}: {data}")
        except socket.error as e:
            logger.error(f"[{self.identifier}] Connection error with client {identifier}: {e}")
        finally:
            with self.lock:
                connection.close()
                self.client_connections.pop(identifier, None)
                logger.info(f"[{self.identifier}] Disconnected from client {identifier}")

    def _handle_peer(self, connection, identifier):
        """
        Handles communication with a peer.
        """
        try:
            while self.running:
                data = connection.recv(1024).decode()
                if not data:
                    continue
                message_type, params = cpv_utils.parse_message(data)
                if message_type == cpv_utils.RTT_MEASUREMENT_REQUEST:
                    # Respond to RTT measurement request
                    requester_id = params[0]
                    send_time = float(params[1])
                    iteration = int(params[2])
                    response_time = time.time()
                    message = cpv_utils.construct_message(
                        cpv_utils.RTT_MEASUREMENT_RESPONSE, self.identifier, response_time, iteration
                    )
                    connection.sendall(message.encode())
                elif message_type == cpv_utils.RTT_MEASUREMENT_RESPONSE:
                    # Handle RTT measurement response
                    responder_id = params[0]
                    response_time = float(params[1])
                    iteration = int(params[2])
                    self._handle_rtt_response(responder_id, response_time, iteration)
                elif message_type == cpv_utils.FORWARD_TIMESTAMP:
                    # Handle forwarded timestamp
                    sender_id = params[0]
                    timestamp = float(params[1])
                    iteration = int(params[2])
                    self._handle_timestamp_from_client(sender_id, timestamp, iteration)
                elif message_type == cpv_utils.TIMESTAMP:
                    # Handle direct timestamp from peer (if applicable)
                    sender_id = params[0]
                    timestamp = float(params[1])
                    iteration = int(params[2])
                    self._handle_timestamp_from_peer(sender_id, timestamp, iteration)
                elif message_type == cpv_utils.START_MEASUREMENTS:
                    # Start measurements
                    session_id = params[0]
                    iterations = int(params[1])
                    self.session_id = session_id
                    self.measure_delays(iterations)
                else:
                    logger.info(f"[{self.identifier}] Received from {identifier}: {data}")
        except socket.error as e:
            logger.error(f"[{self.identifier}] Connection error with {identifier}: {e}")
        finally:
            with self.lock:
                connection.close()
                self.connections.pop(identifier, None)
                logger.info(f"[{self.identifier}] Disconnected from peer {identifier}")

    def connect_to_peers(self):
        """
        Connects to all predefined peers in the P2P network.
        """
        for identifier, (peer_host, peer_port) in self.peers.items():
            self.connect(identifier, peer_host, peer_port)

    def connect(self, identifier, peer_host, peer_port):
        """
        Establishes an outgoing connection to a peer.
        """
        if identifier in self.connections and self.connections[identifier].get("outgoing"):
            logger.info(f"[{self.identifier}] Already connected to {identifier} (outgoing). Skipping.")
            return

        try:
            outgoing_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            outgoing_socket.connect((peer_host, peer_port))
            message = cpv_utils.construct_message(cpv_utils.HELLO, self.identifier)
            outgoing_socket.sendall(message.encode())
            with self.lock:
                if identifier not in self.connections:
                    self.connections[identifier] = {"incoming": None, "outgoing": outgoing_socket}
                else:
                    self.connections[identifier]["outgoing"] = outgoing_socket

            logger.info(f"[{self.identifier}] Outgoing connection to {identifier} ({peer_host}:{peer_port})")
            threading.Thread(
                target=self._handle_peer, args=(outgoing_socket, identifier), daemon=True
            ).start()
        except socket.error as e:
            logger.error(f"[{self.identifier}] Failed to connect to {identifier}: {e}")

    def measure_delays(self, iterations):
        """
        Measures delays using mp and av protocols over a given number of iterations.
        """
        for iteration in range(1, iterations + 1):
            logger.info(f"[{self.identifier}] Starting iteration {iteration}/{iterations}")
            # Run mp protocol
            self.mp_protocol(iteration)
            # Run av protocol
            self.av_protocol(iteration)
            logger.info(f"[{self.identifier}] Iteration {iteration}/{iterations} completed.")
            # Reset data structures for next iteration
            self.dic_dcj_sums.clear()
            self.min_sums.clear()
            self.verifier_measurements.clear()
            self.av_delays.clear()
            self.forwarded_timestamps.clear()

    def mp_protocol(self, iteration):
        """
        Implements the mp protocol for delay measurement.
        """
        # Step 1: Send timestamp to client
        self._send_timestamp_to_client(iteration)
        # Wait for timestamps to propagate
        time.sleep(1)
        # Step 2: Compute min(dic + dcj, djc + dci)
        self._compute_min_sums(iteration)
        # Store delays
        self._store_mp_delays(iteration)

    def _send_timestamp_to_client(self, iteration):
        """
        Sends the current timestamp to the client.
        """
        current_time = time.time()
        message = cpv_utils.construct_message(
            cpv_utils.TIMESTAMP, self.identifier, current_time, iteration
        )
        with self.lock:
            for client_id, client_conn in self.client_connections.items():
                try:
                    client_conn.sendall(message.encode())
                    logger.info(f"[{self.identifier}] Sent timestamp to client {client_id}")
                except socket.error as e:
                    logger.error(f"[{self.identifier}] Error sending timestamp to {client_id}: {e}")

    def _handle_timestamp_from_client(self, sender_id, timestamp, iteration):
        """
        Handles a timestamp forwarded by the client from another verifier.
        """
        receive_time = time.time()
        dic_dcj = receive_time - timestamp
        key = (sender_id, self.identifier, iteration)
        with self.lock:
            self.dic_dcj_sums[key] = dic_dcj
        logger.info(f"[{self.identifier}] Received timestamp from {sender_id}, dic + dcj = {dic_dcj:.6f}")

    def _compute_min_sums(self, iteration):
        """
        Computes min(dic + dcj, djc + dci) for all pairs.
        """
        with self.lock:
            server_ids = set([self.identifier] + list(self.peers.keys()))
            for i in server_ids:
                for j in server_ids:
                    if i != j:
                        key1 = (i, j, iteration)
                        key2 = (j, i, iteration)
                        dic_dcj = self.dic_dcj_sums.get(key1)
                        djc_dci = self.dic_dcj_sums.get(key2)
                        if dic_dcj is not None and djc_dci is not None:
                            min_sum = min(dic_dcj, djc_dci)
                            self.min_sums[(i, j)] = min_sum
                            logger.info(f"[{self.identifier}] min(dic + dcj, djc + dci) for ({i}, {j}): {min_sum:.6f}")

    def _store_mp_delays(self, iteration):
        """
        Stores the min(dic + dcj, djc + dci) values calculated from the mp protocol.
        """
        data = {'min_sums': {f"{k[0]}_{k[1]}": v for k, v in self.min_sums.items()}}
        cpv_utils.log_delays(
            self.delays_mp_file, self.session_id, iteration, data, self.lock
        )

    def av_protocol(self, iteration):
        """
        Implements the av protocol for delay measurement.
        """
        # Measure RTTs with other verifiers
        for verifier_id, sockets in self.connections.items():
            if sockets.get("outgoing"):
                self._measure_rtt_with_verifier(verifier_id, sockets["outgoing"], iteration)
        # Wait for RTT measurements
        time.sleep(1)
        # Delays are computed upon receiving responses
        self._store_av_delays(iteration)

    def _measure_rtt_with_verifier(self, verifier_id, verifier_conn, iteration):
        """
        Measures RTT with another verifier.
        """
        try:
            send_time = time.time()
            message = cpv_utils.construct_message(
                cpv_utils.RTT_MEASUREMENT_REQUEST, self.identifier, send_time, iteration
            )
            verifier_conn.sendall(message.encode())
            # Store send_time
            key = (verifier_id, iteration)
            with self.lock:
                self.verifier_measurements[key] = {'send_time': send_time}
        except socket.error as e:
            logger.error(f"[{self.identifier}] Error measuring RTT with {verifier_id}: {e}")

    def _handle_rtt_response(self, responder_id, response_time, iteration):
        """
        Handles RTT measurement response from another verifier.
        """
        receive_time = time.time()
        key = (responder_id, iteration)
        with self.lock:
            send_time = self.verifier_measurements.get(key, {}).get('send_time')
            if send_time:
                rtt = receive_time - send_time
                delay = rtt / 2
                self.av_delays[key] = delay
                logger.info(f"[{self.identifier}] RTT with {responder_id}: {rtt:.6f}, delay: {delay:.6f}")
            else:
                logger.warning(f"[{self.identifier}] Missing send_time for RTT with {responder_id}")

    def _store_av_delays(self, iteration):
        """
        Stores the delays calculated from the av protocol.
        """
        with self.lock:
            delays = {k[0]: v for k, v in self.av_delays.items() if k[1] == iteration}
        data = {'delays': delays}
        cpv_utils.log_delays(
            self.delays_av_file, self.session_id, iteration, data, self.lock
        )

    def list_connections(self):
        """
        Lists all active connections to peers and clients.
        """
        with self.lock:
            logger.info(f"[{self.identifier}] Connections:")
            for identifier, sockets in self.connections.items():
                if sockets.get("incoming") or sockets.get("outgoing"):
                    logger.info(f"  - Peer: {identifier}")
            for client_id in self.client_connections.keys():
                logger.info(f"  - Client: {client_id}")

    def shutdown(self):
        """
        Gracefully shuts down the server, closing all connections and notifying peers.
        """
        logger.info(f"[{self.identifier}] Shutting down...")
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
            command = input("Enter command (list/connect/measure_delays/close): ").strip().lower()
            if command == "list":
                self.list_connections()
            elif command == "connect":
                self.connect_to_peers()
            elif command == "measure_delays":
                self.session_id = str(uuid.uuid4())  # New session ID
                iterations = 10  # Number of iterations
                self._broadcast_start_measurements(iterations)
            elif command == "close":
                self.shutdown()
                break
            else:
                logger.info("Available commands: list, connect, measure_delays, close")

    def _broadcast_start_measurements(self, iterations):
        """
        Sends a message to all connected entities to start measurements.
        """
        message = cpv_utils.construct_message(
            cpv_utils.START_MEASUREMENTS, self.session_id, iterations
        )
        with self.lock:
            # Send to other verifiers
            for verifier_id, sockets in self.connections.items():
                if sockets.get("outgoing"):
                    try:
                        sockets["outgoing"].sendall(message.encode())
                    except socket.error as e:
                        logger.error(f"[{self.identifier}] Error sending start message to {verifier_id}: {e}")
            # Send to clients
            for client_id, client_conn in self.client_connections.items():
                try:
                    client_conn.sendall(message.encode())
                except socket.error as e:
                    logger.error(f"[{self.identifier}] Error sending start message to client {client_id}: {e}")
