# cpv_utils.py

import json
import time
import threading

# Constants for message types
HELLO = "HELLO"
TIMESTAMP = "TIMESTAMP"
FORWARD_TIMESTAMP = "FORWARD_TIMESTAMP"
OWD_MEASUREMENT_REQUEST = "OWD_MEASUREMENT_REQUEST"
OWD_MEASUREMENT_RESPONSE = "OWD_MEASUREMENT_RESPONSE"
RTT_MEASUREMENT_REQUEST = "RTT_MEASUREMENT_REQUEST"
RTT_MEASUREMENT_RESPONSE = "RTT_MEASUREMENT_RESPONSE"
START_MEASUREMENTS = "START_MEASUREMENTS"

def parse_message(data):
    """
    Parses a message string and returns a tuple of (message_type, params).

    Args:
        data (str): The message string to parse.

    Returns:
        tuple: A tuple containing the message type and a list of parameters.
    """
    parts = data.strip().split()
    if not parts:
        return None, None
    message_type = parts[0]
    params = parts[1:]
    return message_type, params

def construct_message(message_type, *args):
    """
    Constructs a message string from the message type and arguments.

    Args:
        message_type (str): The type of the message.
        *args: Additional arguments to include in the message.

    Returns:
        str: The constructed message string.
    """
    return f"{message_type} {' '.join(map(str, args))}"

def log_delays(filename, session_id, iteration, data, lock=None):
    """
    Logs the delay data to the specified file.

    Args:
        filename (str): The name of the file to log to.
        session_id (str): The session ID for the measurement.
        iteration (int): The iteration number.
        data (dict): The data to log.
        lock (threading.Lock, optional): A lock to ensure thread safety.

    """
    entry = {
        "session_id": session_id,
        "iteration": iteration,
        "data": data,
        "timestamp": time.time()
    }
    if lock:
        lock.acquire()
    try:
        with open(filename, "a") as file:
            json.dump(entry, file)
            file.write("\n")
    finally:
        if lock:
            lock.release()
