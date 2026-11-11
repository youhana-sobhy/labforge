"""Pick free subnets for lab management and link networks so labs never collide."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable, Iterator


def free_subnets(pool: str, prefixlen: int, taken: Iterable[str]) -> Iterator[str]:
    taken_nets = [ipaddress.ip_network(t, strict=False) for t in taken]
    for sub in ipaddress.ip_network(pool).subnets(new_prefix=prefixlen):
        if not any(sub.overlaps(t) for t in taken_nets):
            yield str(sub)
