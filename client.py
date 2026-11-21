#!/usr/bin/env python3
"""TCP client: requests content through the controller virtual IP."""
import argparse
import json
import socket
import time

def request(vip, port, size):
    start = time.perf_counter()
    with socket.create_connection((vip, port), timeout=2) as conn:
        conn.settimeout(4)
        conn.sendall(f"GET {size}\n".encode("ascii"))
        stream = conn.makefile("rb")
        header = stream.readline().decode("ascii").strip()
        if "|" not in header:
            raise RuntimeError(f"invalid server response: {header}")
        server, length = header.rsplit("|", 1)
        expected = int(length)
        got = 0
        while got < expected:
            chunk = stream.read(min(65536, expected - got))
            if not chunk:
                raise RuntimeError("incomplete content response")
            got += len(chunk)
    elapsed = time.perf_counter() - start
    return {"server": server, "bytes": got, "response_ms": elapsed * 1000,
            "throughput_mbps": got * 8 / elapsed / 1_000_000}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--client", required=True)
    p.add_argument("--vip", default="10.0.0.100")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--requests", type=int, default=10)
    p.add_argument("--bytes", type=int, default=65536)
    p.add_argument("--retries", type=int, default=3)
    args = p.parse_args()
    for i in range(args.requests):
        error = "request failed"
        request_started = time.perf_counter()
        for attempt in range(args.retries + 1):
            try:
                row = request(args.vip, args.port, args.bytes)
                elapsed = time.perf_counter() - request_started
                row["response_ms"] = elapsed * 1000
                row["throughput_mbps"] = row["bytes"] * 8 / elapsed / 1_000_000
                row.update({"client": args.client, "sequence": i + 1, "ok": True,
                            "attempts": attempt + 1})
                break
            except Exception as exc:
                error = str(exc)
                if attempt < args.retries:
                    time.sleep(0.25 * (attempt + 1))
        else:
            row = {"client": args.client, "sequence": i + 1, "ok": False,
                   "attempts": args.retries + 1, "error": error}
        print(json.dumps(row), flush=True)

if __name__ == "__main__":
    main()
