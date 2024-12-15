import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.cpv.server_architecture import Server

def main():
    host = '192.168.192.84'
    port = 9702
    identifier = 'server2'
    peers = {
        'server1': ('192.168.192.103', 9701),
        'server3': ('192.168.192.138', 9704)
    }

    test_dir = os.path.dirname(os.path.abspath(__file__))
    delays_mp_file = os.path.join(test_dir, "delays_mp.txt")
    delays_av_file = os.path.join(test_dir, "delays_av.txt")

    server = Server(
        host,
        port,
        peers,
        identifier,
        delays_mp_file=delays_mp_file,
        delays_av_file=delays_av_file
    )
    server.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down server...")
        server.shutdown()

if __name__ == '__main__':
    main()
