# Smart Content Delivery System - Mininet + SDN

## Robust random-condition version
This copy adds a sixth, longer dynamic-routing scenario. While two clients are actively sending requests, a background disturbance thread changes server-path delays at random intervals and sometimes temporarily disables and restarts a server. The event timing is independent of the old 20-request scenario boundaries. Clients retry transient connection/read failures up to three times with short backoff. Failed-after-retry requests are recorded rather than aborting the full experiment; the summary separates successful and failed requests. Response time for a retried request includes the failed attempts and retry delays.

The original five scenarios remain for comparison. Random events are printed in the terminal. The new CSV columns `attempts` and `status` make retries/final failures visible. This remains a Mininet emulation with controller availability explicitly updated by the experiment driver, rather than autonomous health monitoring.

To use this copy in the VM, copy `robust_version` into `~/scds/` so that it can reuse the existing `~/scds/.venv`, then run `cd ~/scds/robust_version && ./run_demo.sh`. The script detects and uses the parent virtual environment automatically.

## Project status
This is the Mininet-based implementation required by the course rubric. The earlier standalone TCP simulator remains in the parent folder as a fallback/reference. This version uses a real Mininet topology, an Open vSwitch bridge speaking OpenFlow 1.3, an OS-Ken controller, TCP content servers, and TCP clients.

## Architecture
- Two client hosts (client1, client2) send TCP GET requests to virtual IP 10.0.0.100:8080.
- One OpenFlow 1.3 switch (s1) connects the clients to three content servers.
- OS-Ken receives the first packet of each TCP connection and installs forward and reverse flow rules. The rules rewrite the virtual destination/source IP so clients keep using the VIP.
- The controller selects a backend using response-time EWMA and path-delay data; static mode pins new connections to server_a.
- A local UDP control interface lets the experiment driver report measured samples, set path delay, switch static/dynamic mode, and disable a failed server.
- Mininet TCLink and Linux tc netem apply actual link delay. The failure scenario stops the selected server process and excludes it from new forwarding decisions.

## Windows setup
Mininet is Linux-based. Mininet maintainers recommend their prebuilt Ubuntu VM for Windows; the Mininet 2.3.0 release page recommends the Ubuntu 20.04.1 VM image. Download/install Oracle VirtualBox for Windows, then download and import that official Mininet VM. The VM archive is large (roughly 0.6-1 GB compressed) and requires additional disk space after import.

1. Install VirtualBox from Oracle's official Downloads page.
2. Download the Ubuntu 20.04.1 Mininet VM asset from the Mininet 2.3.0 release page and import its OVF into VirtualBox. The official image is about 1 GB compressed and about 2 GB after extraction.
3. Boot the VM and sign in with the official image credentials (username mininet, password mininet). If virtualization is disabled, enable Intel VT-x/AMD-V in firmware and restart. If Windows requests administrator approval or a restart, complete that yourself.
4. Copy this mininet project folder into the Linux VM. A VirtualBox shared folder is convenient when Guest Additions are available; otherwise transfer the project over SSH/SCP using the VM host-only network adapter. The course rubric requests publication to GitHub, but the current package is prepared locally only.

Official setup references: [Mininet VM installation guidance](https://mininet.org/download/), [Mininet 2.3.0 release and VM image](https://github.com/mininet/mininet/releases/tag/2.3.0), [VirtualBox downloads](https://www.virtualbox.org/wiki/Downloads).

## Prepare the Linux VM
In the project folder inside Ubuntu, run:

~~~bash
sudo apt update
sudo apt install -y openvswitch-switch python3-venv python3-pip
mn --version
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
~~~

## Run
From the project folder in the Linux VM:

~~~bash
chmod +x run_demo.sh
./run_demo.sh
~~~

The script starts the OS-Ken controller, creates the Mininet topology, runs the experiment, and cleans up Mininet. It writes one row per TCP request to results.csv, scenario averages to summary.json, and OpenFlow messages to controller.log.

For interactive inspection, start the controller in one terminal with .venv/bin/osken-manager controller.py, then in a second terminal run:

~~~bash
sudo mn --custom topology.py --topo smartcontent --controller=remote,ip=127.0.0.1,port=6633 --switch ovs,protocols=OpenFlow13
~~~

The scripted demonstration is the reproducible route for capturing the required comparison.

## Experiments
The reproducible demo runs 20 requests per condition (10 from each of two clients):
1. Static server_a, normal links.
2. Dynamic selection, normal links.
3. Static server_a, with 180 ms delay on its server link.
4. Dynamic selection under the same congestion.
5. Dynamic mode after stopping and marking the selected backend unavailable.

The CSV includes client, request number, selected backend, response time, throughput, and bytes transferred. Link delays and application service delays are documented in topology.py, controller.py, and run_demo.py.

## Troubleshooting
- No switch connection: confirm the controller is listening on TCP port 6633 and s1 uses OpenFlow 1.3. Check controller.log.
- No server selected: check the UDP control API on 127.0.0.1:9999 and confirm a server is enabled.
- VIP unreachable: both clients need a permanent neighbor entry for 10.0.0.100 using 00:00:00:00:00:99; run_demo.py configures it.
- Mininet permission error: run the lab with sudo; Mininet needs root to manage virtual interfaces and namespaces.
- VirtualBox cannot start the VM: verify hardware virtualization and available memory/disk.

## Reproduction and submission checklist
- Source/topology: controller.py, topology.py, server.py, client.py
- Setup/configuration: requirements.txt and OpenFlow/endpoints configured in source
- Experiment automation: run_demo.py, run_demo.sh
- Tests: TEST_PLAN.md
- Results: generated results.csv and controller.log after the VM run
- GitHub: the course rubric asks for a GitHub repository. The files are prepared locally; publish them to a repository after confirming its URL and public/private visibility.
