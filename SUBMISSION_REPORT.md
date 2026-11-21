# Smart Content Delivery System

## Robustness extension (not yet run in Mininet)
This version preserves the original implementation and adds a sixth dynamic scenario with randomly timed path-delay and server-availability changes during active client traffic. Clients retry transient request failures up to three times, and the CSV/summary distinguish successful requests from failures after retries. The original measurements below describe the earlier five-scenario run only; rerun this version in Mininet before reporting results for the new scenario.

## Abstract
This project uses TCP socket programming and a programmable OpenFlow network to serve content from multiple backends. Two Mininet clients request a virtual service address. An OS-Ken SDN controller dynamically chooses an available server and installs forward and reverse OpenFlow 1.3 rules. Experiments compare static and adaptive forwarding under normal conditions, link congestion, and server failure.

## Problem and objectives
A fixed server can become a bottleneck or fail. The goal is to route each new TCP connection to a suitable available server, preserve the virtual service address for clients, and evaluate delivery performance under changing conditions.

## Topology and communication
The Mininet topology contains two clients, one Open vSwitch, and three content servers. The switch connects to an OS-Ken controller over OpenFlow 1.3. Each client uses TCP to request a 64 KiB object at VIP 10.0.0.100:8080. The controller rewrites the destination to the selected backend and installs reverse translation so the response appears to come from the VIP.

Topology overview:

> Client 1 --\
>            +-- Open vSwitch s1 -- OpenFlow 1.3 -- OS-Ken controller
> Client 2 --/             |
>                           +-- Server A (10.0.0.11)
>                           +-- Server B (10.0.0.12)
>                           +-- Server C (10.0.0.13)


## Selection policy
The controller supports static and dynamic mode. Static mode sends new TCP sessions to server_a while it is healthy. Dynamic mode scores each healthy backend using response-time EWMA plus path delay, then selects the lowest score. Response measurements are reported after each experiment round. If the selected server fails, the runner stops its server process and marks it unavailable; future sessions use a surviving backend.

## Implementation
- client.py: TCP client, response framing, byte count, latency and throughput measurement.
- server.py: concurrent TCP server returning a named content object with configurable service delay.
- topology.py: Mininet hosts, OpenFlow 1.3 switch, and shaped links.
- controller.py: OS-Ken application, VIP selection, bidirectional translation flow rules, L2 learning/flooding for ARP, and experiment control API.
- run_demo.py and run_demo.sh: repeatable startup, condition changes, client concurrency, server outage, measurement output, and cleanup.

## Evaluation
The script runs twenty TCP requests per condition, with two clients running concurrently. Conditions are static-normal, dynamic-normal, static-congested, dynamic-congested, and dynamic-after-server-failure. Response time is measured from TCP connect through receipt of the complete object. Throughput is payload bits divided by elapsed seconds. results.csv contains per-request observations.

## Results
The following measurements are from the completed Mininet run shown in the terminal. Each condition contains 20 requests, with two clients running concurrently (10 requests per client). Values are means reported by the runner; timings depend on VM host load.

| Condition | Mean response time | Mean throughput | Forwarding counts |
|---|---:|---:|---|
| Static baseline - normal | 78.61 ms | 6.70 Mbps | server A: 20 |
| Dynamic - normal | 149.91 ms | 3.51 Mbps | server B: 20 |
| Static baseline - congested | 779.98 ms | 0.67 Mbps | server A: 20 |
| Dynamic - congested | 231.96 ms | 2.27 Mbps | server C: 20 |
| Dynamic - selected server failure | 228.87 ms | 2.29 Mbps | server C: 20 |

Under normal conditions, the static baseline outperformed dynamic selection in this run: its mean response time was 78.61 ms versus 149.91 ms, and its mean throughput was 6.70 Mbps versus 3.51 Mbps. Under congestion on server A's path, dynamic selection performed better than the static baseline: 231.96 ms and 2.27 Mbps versus 779.98 ms and 0.67 Mbps. In the failure scenario, all 20 successful requests were served by server C after the selected backend was taken out of service, at 228.87 ms mean response time and 2.29 Mbps mean throughput. These results show the benefit of adaptation under the tested congestion and failure conditions, but do not show a benefit in every condition or prove performance beyond this small emulated topology.

The earlier run artifacts and measurements below are preserved in the original project folder. The robust version’s output files will be generated when its Mininet run completes.

## Limitations
This is a course-scale Mininet emulation. Link delay is applied by Linux traffic control; controller path-delay telemetry is updated by the experiment harness between rounds. The implementation uses a one-switch topology and an explicit server-health event rather than a production active health-check protocol. It supports multiple clients and independent TCP sessions, but is not intended for real CDN deployment.

## Conclusion
The completed Mininet run demonstrates TCP communication, topology construction, controller-installed OpenFlow rules, dynamic backend selection, and rerouting after a backend outage. In the measured run, adaptation improved the congested and failure scenarios, while static routing performed better in the normal scenario. The results are specific to this topology and run and should be interpreted accordingly.
