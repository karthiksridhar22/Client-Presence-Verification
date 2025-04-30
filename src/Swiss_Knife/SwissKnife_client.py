import socket
import os
import hmac
import hashlib
import time
import random
import json
import binascii

# --- Configuration (MUST MATCH SERVER) ---
HOST = '127.0.0.1'
PORT = 65432
KEY_LENGTH_BYTES = 16
NONCE_LENGTH_BYTES = 16
N_ROUNDS = 30
ERROR_RATE = 0.05 # Simulate errors on challenges *received* by the tag
TAG_ID = "TAG_001" # The ID of this tag

# !! IMPORTANT FOR SIMULATION: Use the key printed by the server !!
# In a real tag, this key would be securely stored.
# Replace this with the actual key hex printed by the server when you run it.
SHARED_KEY_HEX = "PASTE_SERVER_KEY_HEX_HERE" # e.g., "a1b2c3d4..."
try:
    SHARED_KEY = bytes.fromhex(SHARED_KEY_HEX)
    if len(SHARED_KEY) != KEY_LENGTH_BYTES:
        raise ValueError(f"Key length mismatch. Expected {KEY_LENGTH_BYTES} bytes.")
except (ValueError, TypeError) as e:
    print(f"[ERROR] Invalid SHARED_KEY_HEX: '{SHARED_KEY_HEX}'. Please paste the hex key from the server output.")
    print(f"Error details: {e}")
    exit(1)


# System-wide constant (must match server)
C_B = b'SystemConstantB'

# --- Helper Functions (Identical to Server) ---
def prf(key, message):
    """Pseudo-Random Function (HMAC-SHA256)."""
    if isinstance(message, str):
        message = message.encode('utf-8')
    elif isinstance(message, list):
         message = b''.join([m.encode('utf-8') if isinstance(m, str) else m for m in message])
    elif not isinstance(message, bytes):
        message = str(message).encode('utf-8')
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

def safe_recv(s, buffer_size=4096):
    """Receive data safely."""
    try:
        data = s.recv(buffer_size)
        if not data:
            print("[!] Server disconnected unexpectedly.")
            return None
        return data
    except ConnectionResetError:
        print("[!] Server connection reset.")
        return None
    except Exception as e:
        print(f"[!] Error receiving data: {e}")
        return None

def safe_send(s, data):
    """Send data safely."""
    try:
        s.sendall(data)
        return True
    except BrokenPipeError:
        print("[!] Server connection broken.")
        return False
    except Exception as e:
        print(f"[!] Error sending data: {e}")
        return False

# --- Client Logic ---
def run_client():
    """Runs the client (tag) logic."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            print(f"[*] Connecting to server {HOST}:{PORT}...")
            s.connect((HOST, PORT))
            print("[+] Connected.")

            # 1. Receive N_A
            n_a = safe_recv(s, NONCE_LENGTH_BYTES)
            if not n_a or len(n_a) != NONCE_LENGTH_BYTES:
                print("[!] Failed to receive valid N_A.")
                return
            print(f"[*] Received N_A: {n_a.hex()}")

            # 2. Generate N_B, compute Z^0, Z^1, send N_B
            n_b = os.urandom(NONCE_LENGTH_BYTES)
            print(f"[*] Generated N_B: {n_b.hex()}")

            # a = f_x(C_B, N_B)
            a = prf(SHARED_KEY, C_B + n_b)
            # Z^0 = a
            z0_full = a
            # Z^1 = a XOR x
            z1_full = xor_bytes(a, SHARED_KEY) # Assuming key 'x' is long enough

            # Get the first N_ROUNDS bits for Z0 and Z1
            z0_bits = bytes_to_bits(z0_full)[:N_ROUNDS]
            z1_bits = bytes_to_bits(z1_full)[:N_ROUNDS]

            if len(z0_bits) < N_ROUNDS or len(z1_bits) < N_ROUNDS:
                 print(f"[!] PRF output too short for {N_ROUNDS} rounds. Need {N_ROUNDS} bits.")
                 return

            print("[*] Sending N_B...")
            if not safe_send(s, n_b): return

            # 3. Rapid Bit Exchange Phase
            challenges_received_prime = [] # c'_i list (potentially with errors)
            print("[*] Starting Rapid Bit Exchange...")
            for i in range(N_ROUNDS):
                # Receive challenge c_i
                c_i = safe_recv(s, 1) # Expecting '0' or '1'
                if not c_i or c_i not in [b'0', b'1']:
                    print(f"[!] Invalid challenge received in round {i+1}. Aborting.")
                    return

                # Simulate channel error on received challenge -> c'_i
                c_prime_i = simulate_channel_error(c_i, ERROR_RATE)
                challenges_received_prime.append(c_prime_i) # Store the (possibly erroneous) bit

                # Select response r'_i = Z^{c'_i}_i
                response_bit = z0_bits[i] if c_prime_i == b'0' else z1_bits[i]
                r_prime_i = str(response_bit).encode('utf-8') # Send as '0' or '1'

                # Send response r'_i
                if not safe_send(s, r_prime_i): return
                # print(f"    Round {i+1}: Recv={c_i.decode()} (-> {c_prime_i.decode()}), Sent={r_prime_i.decode()}")
                time.sleep(0.001) # Small pause

            print("[*] Rapid Bit Exchange finished.")

            # 4. Compute t_B and send auth data
            # t_B = f_x(c_1',...,c_n', ID, N_A, N_B)
            prf_input_tb = b"".join(challenges_received_prime) + TAG_ID.encode('utf-8') + n_a + n_b
            t_b = prf(SHARED_KEY, prf_input_tb)

            # Convert c'_list bytes to strings for JSON
            challenges_received_prime_str = [c.decode('utf-8') for c in challenges_received_prime]

            auth_data = {
                "t_b": t_b.hex(),
                "c_prime_list": challenges_received_prime_str
            }
            print(f"[*] Computed t_B: {t_b.hex()}")
            # print(f"[*] Sending c'_list: {challenges_received_prime_str}")
            print("[*] Sending authentication data...")
            if not safe_send(s, json.dumps(auth_data).encode('utf-8')): return

            # 5. Receive final status and potentially t_A for mutual auth
            final_response_json = safe_recv(s)
            if not final_response_json: return

            try:
                final_response = json.loads(final_response_json.decode('utf-8'))
                status = final_response.get("status")

                if status == "success":
                    print("[+] Server preliminary verification successful.")
                    # Mutual Authentication Check
                    t_a_received_hex = final_response.get("t_a")
                    if t_a_received_hex:
                        print(f"[*] Received t_A for mutual auth: {t_a_received_hex}")
                        t_a_received = bytes.fromhex(t_a_received_hex)
                        # Compute expected t_A = f_x(N_B)
                        expected_t_a = prf(SHARED_KEY, n_b)
                        if hmac.compare_digest(expected_t_a, t_a_received):
                            print("[SUCCESS] Mutual authentication successful! Sending final ACK.")
                            # Send final confirmation
                            safe_send(s, json.dumps({"status": "final_ack"}).encode('utf-8'))
                        else:
                            print("[FAILURE] Mutual authentication failed (t_A mismatch).")
                            # Optionally send rejection
                            safe_send(s, json.dumps({"status": "mutual_auth_fail"}).encode('utf-8'))
                    else:
                        print("[!] Server reported success but did not send t_A for mutual auth.")
                elif status == "fail":
                    reason = final_response.get("reason", "unknown")
                    print(f"[FAILURE] Server rejected authentication. Reason: {reason}")
                else:
                    print(f"[!] Received unknown status from server: {status}")

            except (json.JSONDecodeError, KeyError, binascii.Error, TypeError) as e:
                print(f"[!] Failed to parse final response from server: {e}")
                print(f"    Raw response: {final_response_json}")


        except ConnectionRefusedError:
            print("[!] Connection refused. Is the server running?")
        except Exception as e:
            print(f"[!] An error occurred: {e}")
        finally:
            print("[-] Client finished.")

if __name__ == "__main__":
    if "PASTE_SERVER_KEY_HEX_HERE" in SHARED_KEY_HEX:
         print("\n[ERROR] Please edit the client script (`swiss_knife_client.py`)")
         print("        and replace 'PASTE_SERVER_KEY_HEX_HERE' with the")
         print("        actual key hex string printed by the server.\n")
    else:
        run_client()

