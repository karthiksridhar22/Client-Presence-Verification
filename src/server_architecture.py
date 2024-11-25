import socket
import threading
import time
import json


class Server:
    def __init__(self, host, port, peers=None, identifier=None):
        """
        Initializes a Server object to act as a verifier in the CPV protocol.

        :param host: The IP address of the server.
        :param port: The port on which the server listens.
        :param peers: Dictionary of peer identifiers mapped to their (host, port) tuples.
        :param identifier: Unique identifier for the server.
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
                        if identifier not in self.connections:
                            self.connections[identifier] = {"incoming": connection, "outgoing": None}
                        else:
                            self.connections[identifier]["incoming"] = connection
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
        Handles communication with a client.
        """
        try:
            while self.running:
                data = connection.recv(1024).decode()
                if not data:
                    continue
                # Handle OWD measurement response from client
                if data.startswith("OWD_MEASUREMENT_RESPONSE"):
                    _, responder_id, response_time_str = data.split()
                    response_time = float(response_time_str)
                    receive_time = time.time()
                    send_time = self.client_measurements.get(identifier, {}).get("send_time")
                    if send_time:
                        # Calculate OWDs
                        owd_self_to_client = response_time - send_time
                        owd_client_to_self = receive_time - response_time
                        # Log OWDs
                        self._log_owd(self.identifier, identifier, owd_self_to_client)
                        self._log_owd(identifier, self.identifier, owd_client_to_self)
                else:
                    print(f"[{self.identifier}] Received from client {identifier}: {data}")
        except socket.error as e:
            print(f"[{self.identifier}] Connection error with client {identifier}: {e}")
        finally:
            with self.lock:
                connection.close()
                self.client_connections.pop(identifier, None)
                print(f"[{self.identifier}] Disconnected from client {identifier}")

    def _handle_peer(self, connection, identifier):
        """
        Handles communication with a peer.
        """
        try:
            while self.running:
                data = connection.recv(1024).decode()
                if not data:
                    continue
                # Handle OWD measurement requests and responses
                if data.startswith("OWD_MEASUREMENT_REQUEST"):
                    _, requester_id, send_time_str = data.split()
                    # Respond immediately
                    response_time = time.time()
                    message = f"OWD_MEASUREMENT_RESPONSE {self.identifier} {response_time}"
                    connection.sendall(message.encode())
                elif data.startswith("OWD_MEASUREMENT_RESPONSE"):
                    _, responder_id, response_time_str = data.split()
                    response_time = float(response_time_str)
                    receive_time = time.time()
                    send_time = self.verifier_measurements.get(identifier, {}).get("send_time")
                    if send_time:
                        # Calculate OWDs
                        owd_self_to_verifier = response_time - send_time
                        owd_verifier_to_self = receive_time - response_time
                        # Log OWDs
                        self._log_owd(self.identifier, identifier, owd_self_to_verifier)
                        self._log_owd(identifier, self.identifier, owd_verifier_to_self)
                else:
                    print(f"[{self.identifier}] Received from {identifier}: {data}")
        except socket.error as e:
            print(f"[{self.identifier}] Connection error with {identifier}: {e}")
        finally:
            with self.lock:
                connection.close()
                self.connections.pop(identifier, None)
                print(f"[{self.identifier}] Disconnected from peer {identifier}")

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

    def measure_delays(self):
        """
        Measures all necessary delays and logs them.
        """
        self.verifier_measurements = {}
        self.client_measurements = {}

        # Measure bidirectional delays with other verifiers
        for verifier_id, sockets in self.connections.items():
            if sockets.get("outgoing"):
                verifier_conn = sockets["outgoing"]
                self._measure_bidirectional_delays_with_verifier(verifier_id, verifier_conn)

        # Measure bidirectional delays with the client
        for client_id, client_conn in self.client_connections.items():
            self._measure_bidirectional_delays_with_client(client_id, client_conn)

        # Allow time for measurements
        time.sleep(1)

        # After measuring OWDs, calculate and log dic + dcj for all i, j
        self._calculate_and_log_dic_dcj_sums()

    def _measure_bidirectional_delays_with_verifier(self, verifier_id, verifier_conn):
        """
        Measures bidirectional OWDs between this verifier and another verifier.
        """
        try:
            # Send a timestamped message to verifier
            send_time = time.time()
            message = f"OWD_MEASUREMENT_REQUEST {self.identifier} {send_time}"
            verifier_conn.sendall(message.encode())
            # Store send_time for later calculation
            self.verifier_measurements[verifier_id] = {"send_time": send_time}
        except socket.error as e:
            print(f"[{self.identifier}] Error measuring OWD with {verifier_id}: {e}")

    def _measure_bidirectional_delays_with_client(self, client_id, client_conn):
        """
        Measures bidirectional OWDs between this verifier and the client.
        """
        try:
            # Send a timestamped message to the client
            send_time = time.time()
            message = f"OWD_MEASUREMENT_REQUEST {self.identifier} {send_time}"
            client_conn.sendall(message.encode())
            # Store send_time for later calculation
            self.client_measurements[client_id] = {"send_time": send_time}
        except socket.error as e:
            print(f"[{self.identifier}] Error measuring OWD with client {client_id}: {e}")

    def _log_owd(self, from_id, to_id, owd_value):
        """
        Logs the OWD between two entities (verifiers or client).
        """
        with self.lock:
            data = {
                "type": "owd",
                "from": from_id,
                "to": to_id,
                "value": round(owd_value, 6)
            }
            with open(self.delays_file, "a") as file:
                json.dump(data, file)
                file.write("\n")

    def _calculate_and_log_dic_dcj_sums(self):
        """
        Calculates and logs dic + dcj for all i != j from 1 to 3, avoiding duplicates.
        """
        # Read the OWDs from the delays file
        owd_data = []
        existing_dic_dcj_pairs = set()
        with self.lock:
            try:
                with open(self.delays_file, "r") as file:
                    for line in file:
                        data = json.loads(line.strip())
                        if data["type"] == "owd":
                            owd_data.append(data)
                        elif data["type"] == "dic+dcj":
                            vi = data["vi"]
                            vj = data["vj"]
                            existing_dic_dcj_pairs.add((vi, vj))
            except FileNotFoundError:
                print(f"[{self.identifier}] Delays file not found.")
                return
        # Build dictionaries of OWDs
        owd_dict = {}
        for entry in owd_data:
            from_id = entry["from"]
            to_id = entry["to"]
            value = entry["value"]
            owd_dict[(from_id, to_id)] = value
        # Calculate dic + dcj for all i != j
        server_ids = ["server1", "server2", "server3"]
        client_id = "client1"
        for vi in server_ids:
            dic = owd_dict.get((vi, client_id), None)
            if dic is None:
                continue
            for vj in server_ids:
                if vi == vj:
                    continue  # Skip cases where vi == vj
                dcj = owd_dict.get((client_id, vj), None)
                if dcj is None:
                    continue
                pair = (vi, vj)
                if pair in existing_dic_dcj_pairs:
                    continue  # Skip if already logged
                sum_dic_dcj = dic + dcj
                # Log the sum
                with self.lock:
                    data = {
                        "type": "dic+dcj",
                        "vi": vi,
                        "vj": vj,
                        "value": round(sum_dic_dcj, 6)
                    }
                    with open(self.delays_file, "a") as file:
                        json.dump(data, file)
                        file.write("\n")
                existing_dic_dcj_pairs.add(pair)  # Add to the set to prevent duplicates within this execution

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
            command = input("Enter command (list/connect/measure_delays/close): ").strip().lower()
            if command == "list":
                self.list_connections()
            elif command == "connect":
                self.connect_to_peers()
            elif command == "measure_delays":
                self.measure_delays()
            elif command == "close":
                self.shutdown()
                break
            else:
                print("Available commands: list, connect, measure_delays, close")
