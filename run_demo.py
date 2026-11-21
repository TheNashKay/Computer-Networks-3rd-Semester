#!/usr/bin/env python3
"""Start Mininet, run static/dynamic/congestion/failure trials, write results.csv."""
import csv
import json
import random
import socket
import statistics
import threading
import time
from pathlib import Path

from mininet.link import TCLink
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.log import setLogLevel
from topology import SmartContentTopo

ROOT = Path(__file__).resolve().parent
VIP_MAC = "00:00:00:00:00:99"
SERVER_CONFIG = {
    "server_a": ("server_a", 12, "10.0.0.11"),
    "server_b": ("server_b", 25, "10.0.0.12"),
    "server_c": ("server_c", 40, "10.0.0.13"),
}
PROCESSES = {}

def control(command):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2)
    try:
        sock.sendto(json.dumps(command).encode(), ("127.0.0.1", 9999))
        raw, _ = sock.recvfrom(8192)
        answer = json.loads(raw.decode())
        if not answer.get("ok"):
            raise RuntimeError(answer.get("error", "controller rejected command"))
        return answer["result"]
    finally:
        sock.close()

def set_path(net, name, delay_ms):
    host = net.get(name)
    iface = name + "-eth0"
    host.cmd("tc qdisc replace dev %s root netem delay %sms" % (iface, delay_ms))
    control({"action": "path_delay", "server": name, "milliseconds": delay_ms})

def launch_servers(net):
    for name, (host_name, delay, _) in SERVER_CONFIG.items():
        host = net.get(host_name)
        PROCESSES[name] = host.popen(["python3", str(ROOT / "server.py"),
                                      "--name", name, "--delay-ms", str(delay)])
    time.sleep(1)

def launch_clients(net, scenario, writer, requests=10):
    procs = []
    for client in ("client1", "client2"):
        host = net.get(client)
        proc = host.popen(["python3", str(ROOT / "client.py"), "--client", client,
                           "--requests", str(requests), "--bytes", "65536",
                           "--retries", "3"])
        procs.append((client, proc))
    rows = []
    for client, proc in procs:
        stdout, stderr = proc.communicate(timeout=90)
        if proc.returncode != 0:
            raise RuntimeError("%s failed in %s: %s" % (client, scenario, stderr))
        for line in stdout.splitlines():
            row = json.loads(line)
            row["scenario"] = scenario
            rows.append(row)
            writer.writerow([scenario, client, row["sequence"], row.get("server", ""),
                             "%.3f" % row["response_ms"] if row.get("ok") else "",
                             "%.3f" % row["throughput_mbps"] if row.get("ok") else "",
                             row.get("bytes", 0), row.get("attempts", 1),
                             "ok" if row.get("ok") else row.get("error", "failed")])
    successful = [row for row in rows if row.get("ok")]
    for row in successful:
        control({"action": "sample", "server": row["server"],
                 "response_ms": row["response_ms"]})
    counts = {}
    for row in successful:
        counts[row["server"]] = counts.get(row["server"], 0) + 1
    return {
        "scenario": scenario,
        "requests": len(rows),
        "successful": len(successful),
        "failed_after_retries": len(rows) - len(successful),
        "forwarding": counts,
        "mean_response_ms": statistics.mean(r["response_ms"] for r in successful) if successful else None,
        "mean_throughput_mbps": statistics.mean(r["throughput_mbps"] for r in successful) if successful else None,
    }


def random_condition_changes(net, stop_event):
    """Change link delays and server availability at random times during traffic."""
    baseline = {"server_a": 5, "server_b": 12, "server_c": 20}
    while not stop_event.wait(random.uniform(0.5, 1.4)):
        try:
            server_states = control({"action": "status"})["servers"]
            enabled = [name for name, state in server_states.items() if state["enabled"]]
            action = random.choice(["delay", "delay", "availability"])
            if action == "delay":
                name = random.choice(list(SERVER_CONFIG))
                delay = random.choice([baseline[name], random.randint(60, 240)])
                set_path(net, name, delay)
                print("Random event: %s path delay changed to %d ms" % (name, delay), flush=True)
            elif len(enabled) > 1:
                name = random.choice(enabled)
                control({"action": "server", "server": name, "enabled": False})
                process = PROCESSES.get(name)
                if process and process.poll() is None:
                    net.get(name).cmd("kill -TERM %s 2>/dev/null || true" % process.pid)
                    try:
                        process.wait(timeout=2)
                    except Exception:
                        process.terminate()
                print("Random event: %s temporarily unavailable" % name, flush=True)
                if stop_event.wait(random.uniform(0.7, 1.8)):
                    break
                PROCESSES[name] = net.get(name).popen([
                    "python3", str(ROOT / "server.py"), "--name", name,
                    "--delay-ms", str(SERVER_CONFIG[name][1])])
                time.sleep(0.2)
                control({"action": "server", "server": name, "enabled": True})
                print("Random event: %s restored" % name, flush=True)
        except Exception as exc:
            print("Random event warning: %s" % exc, flush=True)

def main():
    setLogLevel("warning")
    net = Mininet(topo=SmartContentTopo(), controller=None, switch=OVSSwitch,
                  link=TCLink, autoSetMacs=False, autoStaticArp=False)
    ctrl = net.addController("c0", controller=RemoteController,
                             ip="127.0.0.1", port=6633)
    summaries = []
    try:
        net.start()
        net.get("s1").cmd("ovs-vsctl set bridge s1 protocols=OpenFlow13")
        for client in ("client1", "client2"):
            net.get(client).cmd("ip neigh replace 10.0.0.100 lladdr %s nud permanent dev %s-eth0"
                                % (VIP_MAC, client))
        launch_servers(net)
        for name in SERVER_CONFIG:
            control({"action": "server", "server": name, "enabled": True})
            set_path(net, name, {"server_a": 5, "server_b": 12, "server_c": 20}[name])

        with (ROOT / "results.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["scenario", "client", "request", "selected_server",
                             "response_time_ms", "throughput_mbps", "bytes", "attempts", "status"])
            control({"action": "mode", "value": "static"})
            summaries.append(launch_clients(net, "Static baseline - normal", writer))

            control({"action": "mode", "value": "dynamic"})
            summaries.append(launch_clients(net, "Dynamic - normal", writer))

            set_path(net, "server_a", 180)
            control({"action": "mode", "value": "static"})
            summaries.append(launch_clients(net, "Static baseline - congested", writer))

            control({"action": "mode", "value": "dynamic"})
            summaries.append(launch_clients(net, "Dynamic - congested", writer))

            # Stop the selected healthy server as well as marking it unavailable.
            selected = control({"action": "status"})["selected"]
            if selected:
                process = PROCESSES[selected]
                net.get(selected).cmd("kill -TERM %s 2>/dev/null || true" % process.pid)
                try:
                    process.wait(timeout=5)
                except Exception:
                    process.terminate()
                control({"action": "server", "server": selected, "enabled": False})
            summaries.append(launch_clients(net, "Dynamic - selected server failure", writer))

            # Changes are injected by elapsed time while 60 requests are in flight,
            # instead of applying one fixed condition to an entire 20-request batch.
            stop_events = threading.Event()
            disturbances = threading.Thread(target=random_condition_changes,
                                             args=(net, stop_events), daemon=True)
            disturbances.start()
            try:
                summaries.append(launch_clients(
                    net, "Dynamic - random conditions", writer, requests=30))
            finally:
                stop_events.set()
                disturbances.join(timeout=3)

        with (ROOT / "summary.json").open("w", encoding="utf-8") as summary_file:
            json.dump(summaries, summary_file, indent=2)
        print("\nScenario results (request counts shown per scenario):")
        for item in summaries:
            print("%s: %s; %s successful, %s failed after retries; %s ms mean; %s Mbps mean" %
                  (item["scenario"], item["forwarding"], item["successful"],
                   item["failed_after_retries"],
                   "%.2f" % item["mean_response_ms"] if item["mean_response_ms"] is not None else "n/a",
                   "%.2f" % item["mean_throughput_mbps"] if item["mean_throughput_mbps"] is not None else "n/a"))
        print("Per-request data: %s" % (ROOT / "results.csv"))
        print("Machine-readable summary: %s" % (ROOT / "summary.json"))
        print("Controller log:   %s" % (ROOT / "controller.log"))
    finally:
        for process in PROCESSES.values():
            if process.poll() is None:
                process.terminate()
        net.stop()

if __name__ == "__main__":
    main()
