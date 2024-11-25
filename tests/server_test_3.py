from src.server_architecture import Server
import time

if __name__ == "__main__":
  server3 = Server('127.0.0.1', 9103, peers={
      'server1': ('127.0.0.1', 9101),
      'server2': ('127.0.0.1', 9102)
  }, identifier='server3')
  server3.start()
  #keep the main program running to allow command input
  try:
      while True:
          time.sleep(1)  # Prevent busy waiting
  except KeyboardInterrupt:
      print("Shutting down server...")
      server3.shutdown()