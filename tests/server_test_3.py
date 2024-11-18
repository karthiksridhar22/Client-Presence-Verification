import time
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from network_architecture import Node

node_c = Node('127.0.0.1', 5012)
node_c.start()

# Give other servers time to start
time.sleep(2)

# Connect to Server A and B
node_c.connect('127.0.0.1', 5010)
node_c.connect('127.0.0.1', 5011)

# Example data to send
time.sleep(2)
node_c.send_data("Hello from Server C!")