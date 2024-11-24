from src.server_architecture import Server
import time

if __name__ == "__main__":
  server2 = Server('127.0.0.1', 8002, peers={
      'server1': ('127.0.0.1', 8001),
      'server3': ('127.0.0.1', 8003)
  }, identifier='server2')
  server2.start()
  #keep the main program running to allow command input
  try:
      while True:
          time.sleep(1)  # Prevent busy waiting
  except KeyboardInterrupt:
      print("Shutting down server...")
      server2.shutdown()