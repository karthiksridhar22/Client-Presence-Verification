import time
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from network_architecture import Node

node_b = Node('127.0.0.1', 5011)
node_b.start()

# Give other servers time to start
time.sleep(5)

# Connect to Server A and C
node_b.connect('127.0.0.1', 5010)
node_b.connect('127.0.0.1', 5012)

# Example data to send
time.sleep(2)
node_b.send_data("Hello from Server B!")
