"""Topology schema: what a catalog template looks like."""

from __future__ import annotations

import ipaddress
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

KindName = Literal["router", "switch", "firewall", "host"]
IFACE_RE = re.compile(r"^(eth[1-9][0-9]*|lo)(\.[1-9][0-9]{0,3})?$")
NODE_RE = re.compile(r"^[a-z][a-z0-9-]{0,20}$")


class SwitchPort(BaseModel):
    access: int | None = Field(None, ge=1, le=4094)
    trunk: list[int] | None = None

    @model_validator(mode="after")
    def one_mode(self) -> SwitchPort:
        if (self.access is None) == (self.trunk is None):
            raise ValueError("a switch port needs exactly one of 'access' or 'trunk'")
        return self


class Node(BaseModel):
    kind: KindName
    label: str | None = None
    pos: tuple[int, int] = (0, 0)
    # interface name -> CIDR, e.g. {"eth1": "10.0.0.1/30", "eth1.10": "10.10.10.1/24", "lo": "1.1.1.1/32"}
    interfaces: dict[str, str] = Field(default_factory=dict)
    gateway: str | None = None  # host default gateway
    routes: dict[str, str] = Field(default_factory=dict)  # prefix (or "default") -> next hop
    config: str | None = None  # router: FRR config (frr.conf syntax)
    ruleset: str | None = None  # firewall: nftables ruleset
    ports: dict[str, SwitchPort] = Field(default_factory=dict)  # switch: port -> VLAN mode
    svi: dict[int, str] = Field(default_factory=dict)  # switch: VLAN -> management IP
    startup: list[str] = Field(default_factory=list)  # long-running commands started after boot (e.g. a web server)

    @field_validator("interfaces")
    @classmethod
    def check_ifaces(cls, v: dict[str, str]) -> dict[str, str]:
        for name, cidr in v.items():
            if not IFACE_RE.match(name):
                raise ValueError(f"bad interface name '{name}' (use eth1, eth1.10, lo)")
            ipaddress.ip_interface(cidr)
        return v


class Check(BaseModel):
    name: str
    type: Literal["ping", "bgp", "ospf", "route", "command"]
    node: str  # node the check runs on
    target: str | None = None  # ping: IP; bgp: neighbor IP; ospf: neighbor router-id; route: prefix
    command: str | None = None  # command: shell command to run
    contains: str | None = None  # command: expected substring
    expect: Literal["pass", "fail"] = "pass"
    timeout: int = Field(45, ge=1, le=300)  # seconds to wait for convergence


class Topology(BaseModel):
    id: str
    name: str
    summary: str
    description: str = ""
    category: str = "General"
    difficulty: Literal["Beginner", "Intermediate", "Advanced"] = "Intermediate"
    ttl_minutes: int = Field(120, ge=5, le=24 * 60)
    tags: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    nodes: dict[str, Node]
    links: list[tuple[str, str]]
    checks: list[Check] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def check_id(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9][a-z0-9-]{1,40}$", v):
            raise ValueError("id must be lowercase letters, digits and dashes")
        return v

    @model_validator(mode="after")
    def check_refs(self) -> Topology:
        for name in self.nodes:
            if not NODE_RE.match(name):
                raise ValueError(f"bad node name '{name}'")
        used: set[str] = set()
        for a, b in self.links:
            for end in (a, b):
                node, _, iface = end.partition(":")
                if node not in self.nodes:
                    raise ValueError(f"link endpoint '{end}' refers to unknown node '{node}'")
                if not re.match(r"^eth[1-9][0-9]*$", iface):
                    raise ValueError(f"link endpoint '{end}' must look like node:ethN")
                if end in used:
                    raise ValueError(f"interface '{end}' is used by more than one link")
                used.add(end)
        for c in self.checks:
            if c.node not in self.nodes:
                raise ValueError(f"check '{c.name}' runs on unknown node '{c.node}'")
            if c.type in ("ping", "bgp", "ospf", "route") and not c.target:
                raise ValueError(f"check '{c.name}' needs a target")
            if c.type == "command" and not c.command:
                raise ValueError(f"check '{c.name}' needs a command")
        return self

    def node_links(self, node: str) -> list[str]:
        """Interfaces of `node` that are wired to a link, in link order."""
        out = []
        for a, b in self.links:
            for end in (a, b):
                n, _, iface = end.partition(":")
                if n == node:
                    out.append(iface)
        return sorted(out, key=lambda i: int(i[3:]))
