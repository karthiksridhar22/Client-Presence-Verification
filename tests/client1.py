import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.cpv.client_architecture import Client

def main():
    identifier = 'client1'
    servers = {
        'server1': ('127.0.0.1', 9601),
        'server2': ('127.0.0.1', 9602),
        'server3': ('127.0.0.1', 9603)
    }

    client = Client(identifier, servers)
    client.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down client...")
        client.shutdown()

if __name__ == '__main__':
    main()
