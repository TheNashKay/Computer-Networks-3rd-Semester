"""Three-server, two-client Mininet topology using an OpenFlow 1.3 OVS switch."""
from mininet.topo import Topo

class SmartContentTopo(Topo):
    def build(self):
        c1 = self.addHost("client1", ip="10.0.0.1/24", mac="00:00:00:00:00:01")
        c2 = self.addHost("client2", ip="10.0.0.2/24", mac="00:00:00:00:00:02")
        a = self.addHost("server_a", ip="10.0.0.11/24", mac="00:00:00:00:00:11")
        b = self.addHost("server_b", ip="10.0.0.12/24", mac="00:00:00:00:00:12")
        c = self.addHost("server_c", ip="10.0.0.13/24", mac="00:00:00:00:00:13")
        sw = self.addSwitch("s1", protocols="OpenFlow13")
        self.addLink(c1, sw, bw=50, delay="2ms")
        self.addLink(c2, sw, bw=50, delay="2ms")
        self.addLink(a, sw, bw=20, delay="5ms")
        self.addLink(b, sw, bw=20, delay="12ms")
        self.addLink(c, sw, bw=20, delay="20ms")

topos = {"smartcontent": lambda: SmartContentTopo()}
