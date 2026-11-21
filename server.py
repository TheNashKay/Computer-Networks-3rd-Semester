#!/usr/bin/env python3
"""TCP content server used by the Mininet lab."""
import argparse
import socketserver
import time

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline().decode("ascii", "replace").strip()
        if not line.startswith("GET "):
            return
        try:
            size = min(max(int(line.split()[1]), 1), 1024 * 1024)
        except (ValueError, IndexError):
            size = 65536
        server = self.server
        time.sleep(server.service_delay_ms / 1000)
        body = (server.server_name.encode() + b"-content-") * ((size // 10) + 1)
        body = body[:size]
        self.wfile.write(f"{server.server_name}|{len(body)}\n".encode("ascii"))
        self.wfile.write(body)

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--delay-ms", type=float, default=10)
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    with Server(("0.0.0.0", args.port), Handler) as server:
        server.server_name = args.name
        server.service_delay_ms = args.delay_ms
        print(f"{args.name} listening on {args.port}, service delay={args.delay_ms} ms", flush=True)
        server.serve_forever()

if __name__ == "__main__":
    main()
