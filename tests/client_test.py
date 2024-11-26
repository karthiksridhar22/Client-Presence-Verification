from src.client_architecture import Client
import time

client = Client(identifier='client1', servers={'server1': ('127.0.0.1', 9101), 'server2': ('127.0.0.1', 9102), 'server3': ('127.0.0.1', 9103)})
client.start()
  #keep the main program running to allow command input
try:
    while True:
        time.sleep(1)  # Prevent busy waiting
except KeyboardInterrupt:
    print("Shutting down server...")
    client.shutdown()