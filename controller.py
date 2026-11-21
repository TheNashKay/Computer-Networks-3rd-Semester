"""OS-Ken OpenFlow 1.3 controller: dynamic TCP VIP-to-server forwarding."""
import json
import socket

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from os_ken.lib import hub
from os_ken.lib.packet import ethernet, ether_types, ipv4, packet, tcp
from os_ken.ofproto import ofproto_v1_3

VIP = "10.0.0.100"
VIP_MAC = "00:00:00:00:00:99"
CONTROL = ("127.0.0.1", 9999)
CLIENT_PORTS = {"10.0.0.1": 1, "10.0.0.2": 2}
SERVERS = {
    "server_a": {"ip": "10.0.0.11", "mac": "00:00:00:00:00:11", "port": 3, "path_ms": 5.0, "service_ms": 12.0, "enabled": True, "ewma_ms": None, "samples": 0},
    "server_b": {"ip": "10.0.0.12", "mac": "00:00:00:00:00:12", "port": 4, "path_ms": 12.0, "service_ms": 25.0, "enabled": True, "ewma_ms": None, "samples": 0},
    "server_c": {"ip": "10.0.0.13", "mac": "00:00:00:00:00:13", "port": 5, "path_ms": 20.0, "service_ms": 40.0, "enabled": True, "ewma_ms": None, "samples": 0},
}

class SmartContentController(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.servers = json.loads(json.dumps(SERVERS))
        self.mode = "dynamic"
        self.mac_to_port = {}
        self._control = hub.spawn(self._control_loop)

    def _score(self, server):
        state = self.servers[server]
        measured = state["ewma_ms"] if state["ewma_ms"] is not None else state["service_ms"]
        return measured + state["path_ms"]

    def _select_server(self):
        healthy = [n for n, s in self.servers.items() if s["enabled"]]
        if not healthy:
            return None
        if self.mode == "static" and "server_a" in healthy:
            return "server_a"
        return min(healthy, key=self._score)

    def _control_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(CONTROL)
        while True:
            raw, peer = sock.recvfrom(8192)
            try:
                command = json.loads(raw.decode("utf-8"))
                result = self._handle_control(command)
                response = {"ok": True, "result": result}
            except Exception as exc:
                response = {"ok": False, "error": str(exc)}
            sock.sendto(json.dumps(response).encode("utf-8"), peer)

    def _handle_control(self, command):
        action = command.get("action")
        if action == "mode":
            value = command["value"]
            if value not in ("static", "dynamic"):
                raise ValueError("mode must be static or dynamic")
            self.mode = value
            return {"mode": value}
        if action == "path_delay":
            name = command["server"]
            self.servers[name]["path_ms"] = max(0.0, float(command["milliseconds"]))
            return {name: self.servers[name]["path_ms"]}
        if action == "server":
            name = command["server"]
            self.servers[name]["enabled"] = bool(command["enabled"])
            return {name: self.servers[name]["enabled"]}
        if action == "sample":
            name = command["server"]
            sample = float(command["response_ms"])
            state = self.servers[name]
            state["ewma_ms"] = sample if state["ewma_ms"] is None else 0.7 * state["ewma_ms"] + 0.3 * sample
            state["samples"] += 1
            return {name: {"ewma_ms": round(state["ewma_ms"], 3), "samples": state["samples"]}}
        if action == "status":
            return {"mode": self.mode, "selected": self._select_server(), "servers": self.servers}
        raise ValueError("unknown action")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features(self, ev):
        dp = ev.msg.datapath
        p, ofp = dp.ofproto_parser, dp.ofproto
        actions = [p.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        dp.send_msg(p.OFPFlowMod(datapath=dp, priority=0, match=p.OFPMatch(),
                                 instructions=[p.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]))
        self.logger.info("OpenFlow 1.3 switch %s connected", dp.id)

    def _add_flow(self, dp, match, actions, priority, timeout=90):
        p, ofp = dp.ofproto_parser, dp.ofproto
        instructions = [p.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(p.OFPFlowMod(datapath=dp, priority=priority, idle_timeout=timeout,
                                 match=match, instructions=instructions))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in(self, ev):
        msg = ev.msg
        dp = msg.datapath
        p, ofp = dp.ofproto_parser, dp.ofproto
        in_port = msg.match["in_port"]
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None or eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        self.mac_to_port.setdefault(dp.id, {})[eth.src] = in_port
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        tcp_pkt = pkt.get_protocol(tcp.tcp)
        if ip_pkt and tcp_pkt and ip_pkt.dst == VIP and tcp_pkt.dst_port == 8080:
            server_name = self._select_server()
            if server_name is None:
                self.logger.warning("No available content server; dropping client request")
                return
            server = self.servers[server_name]
            client_port = CLIENT_PORTS.get(ip_pkt.src)
            if client_port is None:
                self.logger.warning("Unknown client address %s", ip_pkt.src)
                return

            forward_match = p.OFPMatch(in_port=in_port, eth_type=ether_types.ETH_TYPE_IP,
                ip_proto=6, ipv4_src=ip_pkt.src, ipv4_dst=VIP,
                tcp_src=tcp_pkt.src_port, tcp_dst=8080)
            forward_actions = [p.OFPActionSetField(eth_dst=server["mac"]),
                p.OFPActionSetField(ipv4_dst=server["ip"]), p.OFPActionOutput(server["port"])]
            reverse_match = p.OFPMatch(in_port=server["port"], eth_type=ether_types.ETH_TYPE_IP,
                ip_proto=6, ipv4_src=server["ip"], ipv4_dst=ip_pkt.src,
                tcp_src=8080, tcp_dst=tcp_pkt.src_port)
            reverse_actions = [p.OFPActionSetField(eth_src=VIP_MAC),
                p.OFPActionSetField(ipv4_src=VIP), p.OFPActionOutput(client_port)]

            self._add_flow(dp, forward_match, forward_actions, priority=300)
            self._add_flow(dp, reverse_match, reverse_actions, priority=300)
            self.logger.info("Forwarding %s:%d to %s", ip_pkt.src, tcp_pkt.src_port, server_name)
            data = None if msg.buffer_id != ofp.OFP_NO_BUFFER else msg.data
            dp.send_msg(p.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id, in_port=in_port,
                                       actions=forward_actions, data=data))
            return

        # Learn/flood ARP and other traffic so clients and backends can resolve one another.
        table = self.mac_to_port[dp.id]
        out_port = table.get(eth.dst, ofp.OFPP_FLOOD)
        actions = [p.OFPActionOutput(out_port)]
        if out_port != ofp.OFPP_FLOOD:
            match = p.OFPMatch(in_port=in_port, eth_src=eth.src, eth_dst=eth.dst)
            self._add_flow(dp, match, actions, priority=10, timeout=30)
        data = None if msg.buffer_id != ofp.OFP_NO_BUFFER else msg.data
        dp.send_msg(p.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id, in_port=in_port,
                                   actions=actions, data=data))
