"""Device kinds ("drivers"): how each lab target is booted, configured and inspected.

Adding a vendor image (Arista cEOS, Juniper cRPD, Nokia SR Linux, Cisco Nexus 9000v ...) means adding
a class here with its image, boot files and the commands to show and apply config.
"""

from __future__ import annotations

import ipaddress
import os
import shlex
from dataclasses import dataclass, field

from .models import Node

NETSHOOT = os.environ.get("LABFORGE_IMAGE_LINUX", "nicolaka/netshoot:v0.14")
FRR_IMAGES = [
    i for i in [
        os.environ.get("LABFORGE_IMAGE_FRR"),
        "frrouting/frr:v8.4.1",  # verified with every catalog template
        "quay.io/frrouting/frr:10.2.1",
    ] if i
]

FRR_DAEMONS = """\
zebra=yes
bgpd=yes
ospfd=yes
ospf6d=no
ripd=no
ripngd=no
isisd=no
pimd=no
ldpd=no
nhrpd=no
eigrpd=no
babeld=no
sharpd=no
pbrd=no
bfdd=yes
fabricd=no
vrrpd=no
pathd=no
vtysh_enable=yes
zebra_options="  -A 127.0.0.1 -s 90000000"
bgpd_options="   -A 127.0.0.1"
ospfd_options="  -A 127.0.0.1"
bfdd_options="   -A 127.0.0.1"
"""


@dataclass
class Kind:
    name: str
    title: str
    vendor_like: str  # which production platforms this target stands in for
    images: list[str]
    description: str
    mem_mb: int
    command: list[str] | None = None
    sysctls: dict[str, str] = field(default_factory=dict)
    caps: list[str] = field(default_factory=lambda: ["NET_ADMIN", "NET_RAW"])
    console: list[str] = field(default_factory=lambda: ["bash", "-l"])
    config_lang: str = "shell"
    ready_cmd: str | None = None  # exits 0 once the device is fully up
    recover_cmd: str | None = None  # run if ready_cmd keeps failing

    # --- boot ---------------------------------------------------------------------------------------------
    def files(self, node_name: str, node: Node) -> dict[str, str]:
        """Files written into the container before it starts."""
        return {}

    def bootstrap(self, node_name: str, node: Node) -> list[str]:
        """Shell commands run once the container is up and its interfaces are named."""
        return base_ip_cmds(node)

    # --- day-2 ----------------------------------------------------------------------------------------------
    def show_config_cmd(self) -> list[str]:
        return ["sh", "-c", "ip -br addr; echo; ip route"]

    def apply_config_cmd(self, text: str) -> list[str]:
        return ["sh", "-c", text]

    def to_dict(self) -> dict:
        return {
            "name": self.name, "title": self.title, "vendor_like": self.vendor_like,
            "image": self.images[0], "images": self.images, "description": self.description,
            "mem_mb": self.mem_mb, "config_lang": self.config_lang,
        }


def base_ip_cmds(node: Node) -> list[str]:
    cmds: list[str] = ["ip route del default 2>/dev/null || true"]
    for name, cidr in node.interfaces.items():
        if "." in name:
            parent, vid = name.split(".")
            cmds.append(f"ip link add link {parent} name {name} type vlan id {vid}")
        if name != "lo":
            cmds.append(f"ip link set {name} up")
        family = "-6 " if ipaddress.ip_interface(cidr).version == 6 else ""
        cmds.append(f"ip {family}addr add {cidr} dev {name}")
    if node.gateway:
        cmds.append(f"ip route replace default via {node.gateway}")
    for prefix, nh in node.routes.items():
        cmds.append(f"ip route replace {prefix} via {nh}")
    return cmds


class Host(Kind):
    pass


class Switch(Kind):
    """802.1Q switch built from one Linux bridge per VLAN.

    Access ports join their VLAN's bridge untagged. Trunk ports get one tagged sub-interface per allowed
    VLAN (needs the 8021q kernel module, present on every mainstream kernel). This avoids depending on
    bridge VLAN filtering, which some minimal kernels leave out.
    """

    def bootstrap(self, node_name: str, node: Node) -> list[str]:
        cmds = ["ip route del default 2>/dev/null || true"]
        vlans = sorted({m.access for m in node.ports.values() if m.access}
                       | {v for m in node.ports.values() for v in (m.trunk or [])} | set(node.svi))
        for vid in vlans:
            cmds += [f"ip link add vlan{vid} type bridge stp_state 0", f"ip link set vlan{vid} up"]
        for port, mode in node.ports.items():
            cmds.append(f"ip link set {port} up")
            if mode.access:
                cmds.append(f"ip link set {port} master vlan{mode.access}")
            for vid in mode.trunk or []:
                cmds += [f"ip link add link {port} name {port}.{vid} type vlan id {vid}",
                         f"ip link set {port}.{vid} master vlan{vid}", f"ip link set {port}.{vid} up"]
        for vid, cidr in node.svi.items():
            cmds.append(f"ip addr add {cidr} dev vlan{vid}")
        return cmds

    def show_config_cmd(self) -> list[str]:
        script = (
            "echo '# VLAN membership (port -> VLAN)';"
            " for p in /sys/class/net/*/brport; do i=$(basename $(dirname $p));"
            " b=$(basename $(readlink /sys/class/net/$i/master)); echo \"  $i -> $b\"; done | sort;"
            " echo; echo '# MAC address table'; for b in /sys/class/net/vlan*; do v=$(basename $b);"
            " bridge fdb show br $v | grep -v permanent | sed \"s/^/  $v: /\"; done; echo; ip -br addr"
        )
        return ["sh", "-c", script]

    def apply_config_cmd(self, text: str) -> list[str]:
        return ["sh", "-c", "set -e\n" + text + "\necho 'Switch configuration applied.'"]


class Firewall(Kind):
    def files(self, node_name: str, node: Node) -> dict[str, str]:
        return {"/etc/labforge/ruleset.nft": node.ruleset or "flush ruleset\n"}

    def bootstrap(self, node_name: str, node: Node) -> list[str]:
        return base_ip_cmds(node) + ["nft -f /etc/labforge/ruleset.nft"]

    def show_config_cmd(self) -> list[str]:
        return ["sh", "-c", "nft list ruleset; echo; echo '# Interfaces'; ip -br addr; echo; ip route"]

    def apply_config_cmd(self, text: str) -> list[str]:
        # Validate first (-c), then swap the whole ruleset atomically, like a firewall policy push.
        script = (
            "cat > /tmp/candidate.nft <<'LABFORGE_EOF'\n" + text + "\nLABFORGE_EOF\n"
            "nft -c -f /tmp/candidate.nft && nft -f /tmp/candidate.nft"
            " && cp /tmp/candidate.nft /etc/labforge/ruleset.nft && echo 'Ruleset committed.'"
        )
        return ["sh", "-c", script]


class Router(Kind):
    def files(self, node_name: str, node: Node) -> dict[str, str]:
        conf = f"frr defaults datacenter\nhostname {node_name}\nservice integrated-vtysh-config\n!\n"
        conf += (node.config or "").strip() + "\n!\nline vty\n!\n"
        return {
            "/etc/frr/daemons": FRR_DAEMONS,
            "/etc/frr/frr.conf": conf,
            "/etc/frr/vtysh.conf": "service integrated-vtysh-config\n",
        }

    def bootstrap(self, node_name: str, node: Node) -> list[str]:
        # FRR is held back until interfaces carry their final names and addresses (see `command`), so the
        # routing daemons start from a clean, final kernel state every time.
        return base_ip_cmds(node) + ["touch /tmp/.labforge-ready"]

    def show_config_cmd(self) -> list[str]:
        return ["vtysh", "-c", "show running-config"]

    def apply_config_cmd(self, text: str) -> list[str]:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("!")]
        args = ["vtysh", "-c", "configure terminal"]
        for ln in lines:
            args += ["-c", ln]
        args += ["-c", "end", "-c", "write memory"]
        return ["sh", "-c", " ".join(shlex.quote(a) for a in args) + " && echo 'Configuration applied.'"]


KINDS: dict[str, Kind] = {
    "router": Router(
        name="router", title="FRRouting router", vendor_like="Cisco IOS-XR / NX-OS, Juniper (routing)",
        images=FRR_IMAGES, mem_mb=60, config_lang="frr",
        description="Full routing stack (BGP, OSPF, BFD, static) with an industry-standard CLI.",
        sysctls={"net.ipv4.ip_forward": "1"}, caps=["NET_ADMIN", "NET_RAW", "SYS_ADMIN"],
        console=["vtysh"],
        # Wait for final interfaces, then supervise watchfrr so a daemon that dies during startup can be
        # restarted without losing the container (and its interface config).
        command=["sh", "-c", "while [ ! -f /tmp/.labforge-ready ]; do sleep 0.1; done; "
                 "while true; do /usr/lib/frr/docker-start; sleep 1; done"],
        ready_cmd="for d in zebra bgpd ospfd staticd; do [ -n \"$(pidof $d)\" ] || exit 1; done; "
                  "! vtysh -c 'show interface brief' 2>&1 | grep -q 'is not running'",
        recover_cmd="kill $(pidof watchfrr) 2>/dev/null; sleep 0.3; "
                    "for d in zebra bgpd ospfd staticd bfdd; do kill -9 $(pidof $d) 2>/dev/null; done; "
                    "rm -f /var/run/frr/*.pid; true",
    ),
    "switch": Switch(
        name="switch", title="L2 VLAN switch", vendor_like="Cisco Nexus access/leaf, campus switches",
        images=[NETSHOOT], mem_mb=20, command=["sleep", "infinity"],
        description="802.1Q switch with access/trunk ports, MAC learning and SVIs.",
    ),
    "firewall": Firewall(
        name="firewall", title="Stateful firewall", vendor_like="FortiGate, Palo Alto (policy logic)",
        images=[NETSHOOT], mem_mb=20, command=["sleep", "infinity"], config_lang="nft",
        description="Zone-based stateful nftables firewall with VLAN sub-interfaces and routing.",
        sysctls={"net.ipv4.ip_forward": "1"},
    ),
    "host": Host(
        name="host", title="Linux endpoint", vendor_like="Servers, VMs, user PCs",
        images=[NETSHOOT], mem_mb=20, command=["sleep", "infinity"],
        description="Client/server with ping, traceroute, iperf3, curl and tcpdump built in.",
    ),
}

# Production platforms that plug in once their (licensed) container/VM images are available.
VENDOR_ROADMAP = [
    {"name": "Cisco Nexus 9000v", "image": "vrnetlab/cisco_n9kv", "licence": "Cisco CCO download",
     "replaces": "router / switch"},
    {"name": "Juniper vJunos / cRPD", "image": "crpd", "licence": "Juniper trial or licence",
     "replaces": "router"},
    {"name": "FortiGate VM", "image": "vrnetlab/fortinet_fortigate", "licence": "Fortinet VM licence",
     "replaces": "firewall"},
    {"name": "Palo Alto PAN-OS VM", "image": "vrnetlab/paloalto_pa-vm", "licence": "Palo Alto VM licence",
     "replaces": "firewall"},
    {"name": "Arista cEOS", "image": "ceos", "licence": "Free arista.com account", "replaces": "switch"},
    {"name": "Nokia SR Linux", "image": "ghcr.io/nokia/srlinux", "licence": "Free, public image",
     "replaces": "switch"},
    {"name": "Cisco ACI simulator", "image": "VM (OVA)", "licence": "Cisco licence", "replaces": "fabric"},
    {"name": "Nested vSphere (ESXi + vCenter)", "image": "VM (OVA)", "licence": "VMware licence",
     "replaces": "compute"},
]
