from src.network_architecture import Node
import time

if __name__ == "__main__":
  server3 = Node('127.0.0.1', 8003, peers={
      'server1': ('127.0.0.1', 8001),
      'server2': ('127.0.0.1', 8002)
  }, identifier='server3')
  server3.start()
  #keep the main program running to allow command input
  try:
      while True:
          time.sleep(1)  # Prevent busy waiting
  except KeyboardInterrupt:
      print("Shutting down server...")
      server3.shutdown()