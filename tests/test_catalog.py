"""Fast tests: no Docker needed."""

import ipaddress

import pytest

from labforge import catalog
from labforge.kinds import KINDS
from labforge.models import Topology
from labforge.netalloc import free_subnets

TEMPLATES = catalog.load_all()


def test_builtin_catalog_loads():
    assert {"ospf-starter", "firewall-policy", "branch-office", "wan-bgp-triangle", "dc-leaf-spine"} <= set(TEMPLATES)


@pytest.mark.parametrize("tid", sorted(TEMPLATES))
def test_template_is_consistent(tid):
    topo, _ = TEMPLATES[tid]
    assert topo.checks, "every template ships with tests"
    for name, node in topo.nodes.items():
        wired = set(topo.node_links(name))
        for iface in node.interfaces:
            base = iface.split(".")[0]
            assert base == "lo" or base in wired, f"{name}:{iface} has an address but no link"
        for port in node.ports:
            assert port in wired, f"{name}:{port} is a switch port without a link"


@pytest.mark.parametrize("tid", sorted(TEMPLATES))
def test_link_ends_share_a_subnet(tid):
    topo, _ = TEMPLATES[tid]
    for a, b in topo.links:
        ips = []
        for end in (a, b):
            node, iface = end.split(":")
            cidr = topo.nodes[node].interfaces.get(iface)
            if cidr:
                ips.append(ipaddress.ip_interface(cidr))
        if len(ips) == 2:
            assert ips[0].network == ips[1].network, f"{a} and {b} are on different subnets"
            assert ips[0].ip != ips[1].ip


@pytest.mark.parametrize("tid", sorted(TEMPLATES))
def test_every_kind_produces_boot_commands(tid):
    topo, _ = TEMPLATES[tid]
    for name, node in topo.nodes.items():
        kind = KINDS[node.kind]
        assert isinstance(kind.bootstrap(name, node), list)
        kind.files(name, node)


def test_rejects_unknown_node_in_link():
    with pytest.raises(ValueError):
        Topology.model_validate({"id": "bad", "name": "x", "summary": "x",
                                 "nodes": {"a": {"kind": "host"}}, "links": [["a:eth1", "b:eth1"]]})


def test_rejects_reused_interface():
    with pytest.raises(ValueError):
        Topology.model_validate({"id": "bad", "name": "x", "summary": "x",
                                 "nodes": {"a": {"kind": "host"}, "b": {"kind": "host"}, "c": {"kind": "host"}},
                                 "links": [["a:eth1", "b:eth1"], ["a:eth1", "c:eth1"]]})


def test_free_subnets_skip_taken():
    got = list(free_subnets("10.0.0.0/28", 30, ["10.0.0.0/30", "10.0.0.8/29"]))
    assert got == ["10.0.0.4/30"]


def test_router_config_push_is_quoted():
    cmd = KINDS["router"].apply_config_cmd("router bgp 1\n neighbor 1.1.1.1 description it's; rm -rf /\n")
    assert cmd[:2] == ["sh", "-c"]
    assert "'neighbor 1.1.1.1 description it'\"'\"'s; rm -rf /'" in cmd[2]
