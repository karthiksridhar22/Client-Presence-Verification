from cpv.server_architecture import Server
import time

if __name__ == "__main__":
  server1 = Server('127.0.0.1', 9301, peers={
      'server2': ('127.0.0.1', 9302),
      'server3': ('127.0.0.1', 9303)
  }, identifier='server1')
  server1.start()
  #keep the main program running to allow command input
  try:
      while True:
          time.sleep(1)  # Prevent busy waiting
  except KeyboardInterrupt:
      print("Shutting down server...")
      server1.shutdown()