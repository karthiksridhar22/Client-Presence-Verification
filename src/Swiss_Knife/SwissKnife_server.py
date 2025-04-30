import socket
import os
import hmac
import hashlib
import time
import random
import json
import binascii # To convert bytes to hex for PRF input if needed

# --- Configuration ---
HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)
KEY_LENGTH_BYTES = 16 # Length of the shared secret key in bytes (e.g., 128 bits)
NONCE_LENGTH_BYTES = 16 # Length of nonces in bytes
N_ROUNDS = 30       # Number of rapid bit exchange rounds (n)
ERROR_RATE = 0.05   # Probability of a bit flip during rapid exchange simulation
T_THRESHOLD = 3     # Maximum allowed errors (T)
T_MAX_DELAY_MS = 50 # Maximum allowed round-trip time in milliseconds for rapid exchange
SIMULATED_PROCESSING_DELAY_MS = 5 # Add a small delay to simulate tag processing

# System-wide constant (as mentioned in the paper)
C_B = b'SystemConstantB'

# --- Simulated Tag Database (Reader's knowledge) ---
# In a real system, this would be a secure database
TAG_DATABASE = {
    "TAG_001": {
        "id": "TAG_001",
        # Generate a random key for this example run
        "key": os.urandom(KEY_LENGTH_BYTES)
    },
    # Add more tags here if needed
    # "TAG_002": {
    #     "id": "TAG_002",
    #     "key": os.urandom(KEY_LENGTH_BYTES)
    # }
}
# Print the key for the client to use (for simulation purposes only!)
print(f"[*] Server using key for TAG_001: {TAG_DATABASE['TAG_001']['key'].hex()}")

# --- Helper Functions ---
def prf(key, message):
    """Pseudo-Random Function (HMAC-SHA256)."""
    # Ensure message is bytes
    if isinstance(message, str):
        message = message.encode('utf-8')
    elif isinstance(message, list): # Handle list of strings/bytes
         # Convert elements to bytes if they are strings, then join
        message = b''.join([m.encode('utf-8') if isinstance(m, str) else m for m in message])
    elif not isinstance(message, bytes):
        message = str(message).encode('utf-8') # Fallback for other types

    return hmac.new(key, message, hashlib.sha256).digest()

def bytes_to_bits(byte_string):
    """Convert bytes to a list of integer bits (0 or 1)."""
    bits = []
    for byte in byte_string:
        for i in range(8):
            bits.append((byte >> (7 - i)) & 1)
    return bits

def xor_bytes(b1, b2):
    """XOR two byte strings of equal length."""
    return bytes([x ^ y for x, y in zip(b1, b2)])

def simulate_channel_error(bit_char, error_rate):
    """Simulates a potential bit flip on a '0' or '1' byte."""
    if random.random() < error_rate:
        return b'1' if bit_char == b'0' else b'0'
    return bit_char

def safe_recv(conn, buffer_size=4096):
    """Receive data safely, handling potential connection issues."""
    try:
        data = conn.recv(buffer_size)
        if not data:
            print("[!] Client disconnected unexpectedly.")
            return None
        return data
    except ConnectionResetError:
        print("[!] Client connection reset.")
        return None
    except Exception as e:
        print(f"[!] Error receiving data: {e}")
        return None

def safe_send(conn, data):
    """Send data safely, handling potential connection issues."""
    try:
        conn.sendall(data)
        return True
    except BrokenPipeError:
        print("[!] Client connection broken.")
        return False
    except Exception as e:
        print(f"[!] Error sending data: {e}")
        return False

# --- Server Logic ---
def handle_connection(conn, addr):
    """Handles a single client connection."""
    print(f"[+] Connection established from {addr}")
    authenticated = False
    tag_info = None
    shared_key = None

    try:
        # 1. Send N_A
        n_a = os.urandom(NONCE_LENGTH_BYTES)
        print(f"[*] Sending N_A: {n_a.hex()}")
        if not safe_send(conn, n_a): return

        # 2. Receive N_B
        n_b = safe_recv(conn, NONCE_LENGTH_BYTES)
        if not n_b or len(n_b) != NONCE_LENGTH_BYTES:
            print("[!] Failed to receive valid N_B.")
            return
        print(f"[*] Received N_B: {n_b.hex()}")

        # 3. Rapid Bit Exchange Phase (n rounds)
        challenges_sent = []      # c_i list
        responses_received = []   # r_i list
        time_delays = []          # Δt_i list

        print("[*] Starting Rapid Bit Exchange...")
        for i in range(N_ROUNDS):
            # Choose random challenge bit c_i
            c_i = str(random.randint(0, 1)).encode('utf-8') # Send as '0' or '1' byte
            challenges_sent.append(c_i)

            start_time = time.time()
            if not safe_send(conn, c_i): return # Send challenge

            # Receive response r_i
            r_i = safe_recv(conn, 1) # Expecting a single byte '0' or '1'
            end_time = time.time()

            if not r_i or r_i not in [b'0', b'1']:
                 print(f"[!] Invalid response received in round {i+1}. Aborting.")
                 # Send rejection signal (optional, depends on protocol detail)
                 safe_send(conn, json.dumps({"status": "fail", "reason": "invalid_response"}).encode('utf-8'))
                 return

            # Simulate channel error on received response
            r_i = simulate_channel_error(r_i, ERROR_RATE)

            delay_ms = (end_time - start_time) * 1000
            responses_received.append(r_i)
            time_delays.append(delay_ms)
            # print(f"    Round {i+1}: Sent={c_i.decode()}, Recv={r_i.decode()}, Delay={delay_ms:.2f}ms")
            time.sleep(0.001) # Small pause between rounds

        print("[*] Rapid Bit Exchange finished.")

        # 4. Receive t_B and c'_list (challenges received by tag)
        auth_data_json = safe_recv(conn)
        if not auth_data_json: return

        try:
            auth_data = json.loads(auth_data_json.decode('utf-8'))
            t_b_received_hex = auth_data['t_b']
            challenges_received_by_tag_str = auth_data['c_prime_list'] # List of '0'/'1' strings
            t_b_received = bytes.fromhex(t_b_received_hex)
            # Convert string list back to bytes list
            challenges_received_by_tag = [c.encode('utf-8') for c in challenges_received_by_tag_str]
            print(f"[*] Received t_B: {t_b_received_hex}")
            # print(f"[*] Received c'_list: {challenges_received_by_tag_str}")

        except (json.JSONDecodeError, KeyError, binascii.Error, TypeError) as e:
            print(f"[!] Failed to parse authentication data: {e}")
            safe_send(conn, json.dumps({"status": "fail", "reason": "invalid_auth_data"}).encode('utf-8'))
            return

        # 5. Find Tag in DB and Verify t_B
        found_tag = False
        for tag_id, details in TAG_DATABASE.items():
            # Calculate expected t_B = f_x(c_1',...,c_n', ID, N_A, N_B)
            prf_input_tb = b"".join(challenges_received_by_tag) + details['id'].encode('utf-8') + n_a + n_b
            expected_t_b = prf(details['key'], prf_input_tb)

            if hmac.compare_digest(expected_t_b, t_b_received):
                print(f"[+] Tag identified as {tag_id}")
                tag_info = details
                shared_key = details['key']
                found_tag = True
                break

        if not found_tag:
            print("[!] Tag not found in database or t_B verification failed.")
            safe_send(conn, json.dumps({"status": "fail", "reason": "tag_not_found_or_tb_invalid"}).encode('utf-8'))
            return

        # 6. Compute Z^0, Z^1 and Verify Rapid Exchange Responses
        # a = f_x(C_B, N_B)
        a = prf(shared_key, C_B + n_b)
        # Z^0 = a
        z0_full = a
        # Z^1 = a XOR x
        z1_full = xor_bytes(a, shared_key) # Assuming key 'x' is long enough

        # Get the first N_ROUNDS bits for Z0 and Z1
        z0_bits = bytes_to_bits(z0_full)[:N_ROUNDS]
        z1_bits = bytes_to_bits(z1_full)[:N_ROUNDS]

        if len(z0_bits) < N_ROUNDS or len(z1_bits) < N_ROUNDS:
             print(f"[!] PRF output too short for {N_ROUNDS} rounds. Need {N_ROUNDS} bits.")
             safe_send(conn, json.dumps({"status": "fail", "reason": "internal_prf_error"}).encode('utf-8'))
             return

        err_c = 0 # Count of challenge mismatches (c_i != c'_i)
        err_r = 0 # Count of response mismatches (r_i != Z^c_i_i when c_i == c'_i)
        err_t = 0 # Count of timing failures (Δt_i > t_max when c_i == c'_i and r_i == Z^c_i_i)

        print("[*] Verifying rapid exchange responses...")
        for i in range(N_ROUNDS):
            c_i = challenges_sent[i]            # Challenge sent by reader ('0' or '1')
            c_prime_i = challenges_received_by_tag[i] # Challenge received by tag ('0' or '1')
            r_i = responses_received[i]         # Response received by reader ('0' or '1')
            delay = time_delays[i]

            # Determine the expected response bit based on c_i
            expected_bit = z0_bits[i] if c_i == b'0' else z1_bits[i]
            expected_response_char = str(expected_bit).encode('utf-8') # '0' or '1'

            if c_i != c_prime_i:
                err_c += 1
                # print(f"    Round {i+1}: Challenge mismatch (Sent={c_i.decode()}, TagRecv={c_prime_i.decode()})")
            else: # c_i == c_prime_i
                # Check response correctness
                if r_i != expected_response_char:
                    err_r += 1
                    # print(f"    Round {i+1}: Response mismatch (Expected={expected_response_char.decode()}, Recv={r_i.decode()})")
                else: # Correct response received
                    # Check timing
                    if delay > T_MAX_DELAY_MS:
                        err_t += 1
                        # print(f"    Round {i+1}: Timing failed (Delay={delay:.2f}ms > {T_MAX_DELAY_MS}ms)")
                    # else:
                        # print(f"    Round {i+1}: OK (Delay={delay:.2f}ms)")


        total_errors = err_c + err_r + err_t
        print(f"[*] Verification complete: err_c={err_c}, err_r={err_r}, err_t={err_t}, Total={total_errors}")

        # 7. Final Decision and Mutual Authentication
        if total_errors < T_THRESHOLD:
            print(f"[+] Verification successful (Total errors {total_errors} < Threshold {T_THRESHOLD}).")

            # Mutual Authentication: Compute and send t_A = f_x(N_B)
            t_a = prf(shared_key, n_b)
            print(f"[*] Sending t_A for mutual auth: {t_a.hex()}")
            response = {"status": "success", "t_a": t_a.hex()}
            if not safe_send(conn, json.dumps(response).encode('utf-8')): return

            # Wait for final confirmation from tag
            final_ack_json = safe_recv(conn)
            if final_ack_json:
                try:
                    final_ack = json.loads(final_ack_json.decode('utf-8'))
                    if final_ack.get("status") == "final_ack":
                        print("[SUCCESS] Tag authenticated successfully and acknowledged mutual auth.")
                        authenticated = True
                    else:
                        print("[!] Tag rejected mutual authentication or sent invalid final ack.")
                except (json.JSONDecodeError, KeyError):
                     print("[!] Invalid final ack received from tag.")
            else:
                 print("[!] Did not receive final ack from tag.")

        else:
            print(f"[FAILURE] Verification failed (Total errors {total_errors} >= Threshold {T_THRESHOLD}).")
            safe_send(conn, json.dumps({"status": "fail", "reason": "verification_threshold_exceeded"}).encode('utf-8'))

    except Exception as e:
        print(f"[!] An error occurred during connection handling: {e}")
    finally:
        print(f"[-] Closing connection with {addr}. Authenticated: {authenticated}")
        conn.close()

# --- Main Server Loop ---
def start_server():
    """Starts the server and listens for connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Allow reusing address
            s.bind((HOST, PORT))
            s.listen()
            print(f"[*] Server listening on {HOST}:{PORT}")

            while True:
                conn, addr = s.accept()
                # In a real server, you'd likely use threading or asyncio
                # For simplicity, handling one connection at a time here.
                handle_connection(conn, addr)

        except OSError as e:
             print(f"[ERROR] Could not start server: {e}")
        except KeyboardInterrupt:
            print("\n[*] Server shutting down.")

if __name__ == "__main__":
    start_server()
