"""Built-in lab tests: prove the lab (and any change made in it) behaves as intended."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

from .engine import Engine, EngineError
from .models import Check, Topology


def _probe(engine: Engine, lab_id: str, c: Check) -> tuple[bool, str]:
    """One attempt. Returns (condition_true, detail)."""
    if c.type == "ping":
        code, out = engine.exec(lab_id, c.node, ["ping", "-c", "3", "-i", "0.2", "-W", "1", c.target])
        stats = next((ln for ln in out.splitlines() if "packet loss" in ln), out.strip()[-120:])
        return code == 0, stats.strip()
    if c.type == "bgp":
        code, out = engine.exec(lab_id, c.node, ["vtysh", "-c", f"show bgp neighbors {c.target} json"])
        try:
            data = json.loads(out or "{}").get(c.target, {})
        except json.JSONDecodeError:
            return False, out.strip()[:160]
        state = data.get("bgpState", "unknown")
        pfx = sum(
            (af.get("acceptedPrefixCounter") or 0)
            for af in (data.get("addressFamilyInfo") or {}).values() if isinstance(af, dict)
        )
        return state == "Established", f"session {state}, {pfx} prefixes received"
    if c.type == "ospf":
        code, out = engine.exec(lab_id, c.node, ["vtysh", "-c", "show ip ospf neighbor json"])
        try:
            nbrs = json.loads(out or "{}").get("neighbors", {})
        except json.JSONDecodeError:
            return False, out.strip()[:160]
        entry = nbrs.get(c.target) or []
        if isinstance(entry, dict):
            entry = [entry]
        state = (entry[0].get("nbrState") or entry[0].get("state") or "") if entry else "absent"
        return state.startswith("Full"), f"neighbor {c.target} {state or 'unknown'}"
    if c.type == "route":
        code, out = engine.exec(lab_id, c.node, ["ip", "route", "show", c.target])
        line = out.strip().splitlines()[0] if out.strip() else "no route"
        return bool(out.strip()) and code == 0, line
    code, out = engine.exec(lab_id, c.node, c.command or "true")
    ok = code == 0 and (c.contains is None or c.contains in out)
    return ok, (out.strip().splitlines() or [f"exit {code}"])[-1][:160]


def run_check(engine: Engine, lab_id: str, c: Check, fast: bool = False) -> dict:
    t0 = time.time()
    deadline = t0 + (5 if fast else c.timeout)
    want = c.expect == "pass"
    attempts = 0
    while True:
        attempts += 1
        try:
            cond, detail = _probe(engine, lab_id, c)
        except EngineError as e:
            cond, detail = False, str(e)
        if cond == want:
            ok = True
            break
        # Only retry when waiting for something to come up (convergence); a "must fail" check is judged once
        # the network has had time to converge, so a single failed attempt is not enough for 'fail' either.
        if time.time() > deadline or (not want and attempts >= 2):
            ok = cond == want
            break
        time.sleep(2)
    return {
        "name": c.name, "type": c.type, "node": c.node, "target": c.target, "expect": c.expect,
        "ok": ok, "detail": detail, "seconds": round(time.time() - t0, 1), "attempts": attempts,
    }


def run_all(engine: Engine, lab_id: str, topo: Topology, fast: bool = False) -> list[dict]:
    # Positive checks first (they wait for convergence), then "must fail" checks, so a blocked flow is
    # only declared blocked once routing is actually up.
    results: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for phase in ("pass", "fail"):
            idx = [i for i, c in enumerate(topo.checks) if c.expect == phase]
            for i, r in zip(idx, pool.map(lambda i: run_check(engine, lab_id, topo.checks[i], fast), idx), strict=True):
                results[i] = r
    return [results[i] for i in range(len(topo.checks))]
