# Test plan

Run tests in the prepared Linux Mininet VM using ./run_demo.sh. Each scenario uses two client hosts concurrently, ten requests per client, and a 64 KiB TCP response.

| ID | Scenario | Setup/action | Expected behavior | Evidence |
|---|---|---|---|---|
| T1 | Topology connectivity | Start the scripted topology and check OVS/controller connection | One switch, two clients, three servers; switch uses OpenFlow 1.3 | Mininet startup and controller.log |
| T2 | Static baseline | Set controller mode to static | New TCP sessions go to server_a | results.csv forwarding counts |
| T3 | Dynamic normal | Enable dynamic selection | New connections use backend with the lowest response/path score | results.csv and controller flow logs |
| T4 | Congestion response | Apply 180 ms netem delay to server_a link and update path telemetry | Static remains on server_a; dynamic reroutes to a lower-score server | Static/dynamic response times and backend counts |
| T5 | Server failure | Stop the selected server and mark it unavailable | New sessions use a healthy backend; clients still receive complete objects | Successful rows via fallback server |
| T6 | Multiple clients | Run both clients concurrently in every scenario | Each client receives all ten objects | Twenty successful rows per scenario |
| T7 | Performance comparison | Compare static/dynamic normal and static/dynamic congestion | Dynamic mode reduces response time under congestion while preserving delivery | Summary from run_demo.py and raw results.csv |

## Acceptance checks
- Expect 100 successful rows total (five scenarios x twenty requests) unless a row reports an explicit socket/timeout error.
- Server selection must change from server_a to server_b or server_c under congestion in dynamic mode.
- The failure scenario must show no requests to the disabled backend and successful delivery from a surviving server.
- Compare averages from the same run; do not treat results from different machines as identical.
- Repeat the run if a transient failure occurs. Keep the CSV from the final successful run with the report.
