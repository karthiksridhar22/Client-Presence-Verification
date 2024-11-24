from src.network_architecture import Node
import time

if __name__ == "__main__":
  server1 = Node('127.0.0.1', 8001, peers={
      'server2': ('127.0.0.1', 8002),
      'server3': ('127.0.0.1', 8003)
  }, identifier='server1')
  server1.start()
  #keep the main program running to allow command input
  try:
      while True:
          time.sleep(1)  # Prevent busy waiting
  except KeyboardInterrupt:
      print("Shutting down server...")
      server1.shutdown()