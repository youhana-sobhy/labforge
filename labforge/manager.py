"""Lab lifecycle: create, track, extend, test, expire and destroy labs."""

from __future__ import annotations

import json
import logging
import re
import secrets
import string
import threading
import time

from . import catalog, checks
from .engine import Engine, EngineError
from .kinds import KINDS
from .models import Topology
from .settings import settings
from .store import ACTIVE, Store

log = logging.getLogger("labforge.manager")


class LabError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _new_id() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return secrets.choice(string.ascii_lowercase) + "".join(secrets.choice(alphabet) for _ in range(5))


class LabManager:
    def __init__(self, engine: Engine | None = None, store: Store | None = None):
        self.store = store or Store(settings.db_path)
        self.engine = engine or Engine(instance=self.store.instance_id)
        self._stop = threading.Event()
        self._reaper: threading.Thread | None = None
        self._busy: set[str] = set()
        self._lock = threading.Lock()

    # ---- lifecycle --------------------------------------------------------------------------------------
    def create(self, template_id: str, name: str = "", owner: str = "anonymous", ttl_minutes: int | None = None,
               wait: bool = False) -> dict:
        try:
            topo = catalog.get(template_id)
        except KeyError as e:
            raise LabError(f"unknown template '{template_id}'", 404) from e
        if len(self.store.list_labs(active_only=True)) >= settings.max_active_labs:
            raise LabError(f"capacity reached: at most {settings.max_active_labs} labs can run at once", 429)
        ttl = ttl_minutes or topo.ttl_minutes
        if not 5 <= ttl <= settings.max_ttl_minutes:
            raise LabError(f"lifetime must be between 5 and {settings.max_ttl_minutes} minutes")
        owner = (owner or "anonymous").strip()[:40]
        name = re.sub(r"\s+", " ", (name or topo.name)).strip()[:60]
        lab_id = _new_id()
        now = time.time()
        self.store.create_lab({
            "id": lab_id, "name": name, "template": topo.id, "owner": owner, "status": "deploying",
            "created_at": now, "expires_at": now + ttl * 60, "node_count": len(topo.nodes),
            "topology": topo.model_dump_json(),
        })
        self.store.log(lab_id, f"{owner} launched '{name}' from {topo.name} ({len(topo.nodes)} devices, "
                               f"auto-destroy in {ttl} min)")
        t = threading.Thread(target=self._deploy, args=(lab_id, topo), daemon=True, name=f"deploy-{lab_id}")
        t.start()
        if wait:
            t.join()
        return self.get(lab_id)

    def _deploy(self, lab_id: str, topo: Topology) -> None:
        with self._lock:
            self._busy.add(lab_id)
        try:
            runtime = self.engine.deploy(lab_id, topo, lambda m, lvl="info": self.store.log(lab_id, m, lvl))
            lab = self.store.get_lab(lab_id)
            if lab and lab["status"] == "deploying":
                self.store.update_lab(lab_id, status="running", ready_at=time.time(), runtime=json.dumps(runtime))
            else:  # destroyed while deploying
                self.engine.destroy(lab_id)
        except Exception as e:  # noqa: BLE001
            log.exception("deploy failed for %s", lab_id)
            self.store.log(lab_id, f"Deploy failed: {e}", "error")
            self.store.update_lab(lab_id, status="failed", error=str(e)[:500], destroyed_at=time.time())
            try:
                self.engine.destroy(lab_id)
                self.store.log(lab_id, "Cleaned up partial lab", "info")
            except Exception:  # noqa: BLE001
                log.exception("cleanup failed for %s", lab_id)
        finally:
            with self._lock:
                self._busy.discard(lab_id)

    def destroy(self, lab_id: str, reason: str = "user", by: str = "", wait: bool = False) -> dict:
        lab = self._require(lab_id)
        if lab["status"] not in ACTIVE:
            return lab
        if lab["status"] == "destroying":
            return lab
        final = "expired" if reason == "expired" else "destroyed"
        self.store.update_lab(lab_id, status="destroying")
        msg = "Lifetime reached, auto-destroying" if reason == "expired" else f"{by or 'User'} requested teardown"
        self.store.log(lab_id, msg, "warn" if reason == "expired" else "info")

        def run():
            # A deploy still in progress notices the status change and cleans up after itself.
            while lab_id in self._busy:
                time.sleep(0.5)
            try:
                n = self.engine.destroy(lab_id)
                self.store.update_lab(lab_id, status=final, destroyed_at=time.time())
                self.store.log(lab_id, f"Lab destroyed ({n} devices removed, all resources released)", "success")
            except Exception as e:  # noqa: BLE001
                log.exception("destroy failed for %s", lab_id)
                self.store.update_lab(lab_id, status="running", error=str(e)[:500])
                self.store.log(lab_id, f"Destroy failed: {e}", "error")

        t = threading.Thread(target=run, daemon=True, name=f"destroy-{lab_id}")
        t.start()
        if wait:
            t.join()
        return self.get(lab_id)

    def extend(self, lab_id: str, minutes: int) -> dict:
        lab = self._require(lab_id)
        if lab["status"] not in ("deploying", "running"):
            raise LabError("only an active lab can be extended")
        new_exp = max(lab["expires_at"], time.time()) + minutes * 60
        cap = lab["created_at"] + settings.max_ttl_minutes * 60
        if new_exp > cap:
            raise LabError(f"labs can live at most {settings.max_ttl_minutes // 60} hours")
        self.store.update_lab(lab_id, expires_at=new_exp)
        self.store.log(lab_id, f"Lifetime extended by {minutes} min")
        return self.get(lab_id)

    # ---- read -------------------------------------------------------------------------------------------
    def _require(self, lab_id: str) -> dict:
        lab = self.store.get_lab(lab_id)
        if not lab:
            raise LabError(f"lab '{lab_id}' not found", 404)
        return lab

    def _decorate(self, lab: dict, states: dict | None = None) -> dict:
        now = time.time()
        lab = dict(lab)
        lab["remaining_seconds"] = max(0, int(lab["expires_at"] - now)) if lab["status"] in ACTIVE else 0
        lab["deploy_seconds"] = round(lab["ready_at"] - lab["created_at"], 1) if lab.get("ready_at") else None
        if states is not None:
            lab["nodes"] = {
                n: {"kind": spec["kind"], **states.get(n, {"state": "absent"}),
                    "title": KINDS[spec["kind"]].title, "console": KINDS[spec["kind"]].console,
                    "config_lang": KINDS[spec["kind"]].config_lang}
                for n, spec in lab["topology"]["nodes"].items()
            }
        return lab

    def get(self, lab_id: str) -> dict:
        lab = self._require(lab_id)
        states = {}
        if lab["status"] in ACTIVE:
            try:
                states = self.engine.node_states(lab_id)
            except Exception:  # noqa: BLE001
                states = {}
        out = self._decorate(lab, states)
        out["last_checks"] = self.store.last_check_run(lab_id)
        return out

    def list(self, active_only: bool = False) -> list[dict]:
        labs = []
        for lab in self.store.list_labs(active_only=active_only):
            d = self._decorate(lab)
            d.pop("topology", None)
            last = self.store.last_check_run(lab["id"])
            d["last_checks"] = {"passed": last["passed"], "total": last["total"]} if last else None
            labs.append(d)
        return labs

    # ---- day-2 operations ---------------------------------------------------------------------------------
    def _running(self, lab_id: str) -> tuple[dict, Topology]:
        lab = self._require(lab_id)
        if lab["status"] != "running":
            raise LabError(f"lab is {lab['status']}, not running", 409)
        return lab, Topology.model_validate(lab["topology"])

    def _node(self, topo: Topology, node: str):
        if node not in topo.nodes:
            raise LabError(f"unknown node '{node}'", 404)
        return topo.nodes[node]

    def set_link(self, lab_id: str, index: int, up: bool, by: str = "") -> dict:
        """Simulate a link failure (or restore it) by taking both ends administratively down."""
        lab, topo = self._running(lab_id)
        if not 0 <= index < len(topo.links):
            raise LabError("unknown link", 404)
        a, b = topo.links[index]
        for end in (a, b):
            node, iface = end.split(":")
            code, out = self.engine.exec(lab_id, node, ["ip", "link", "set", iface, "up" if up else "down"])
            if code != 0:
                raise LabError(f"could not change {end}: {out.strip()}", 502)
        runtime = lab["runtime"]
        down = set(runtime.get("links_down", []))
        (down.discard if up else down.add)(index)
        runtime["links_down"] = sorted(down)
        self.store.update_lab(lab_id, runtime=json.dumps(runtime))
        what = "restored" if up else "failed (simulated outage)"
        self.store.log(lab_id, f"{by or 'User'}: link {a} <-> {b} {what}", "info" if up else "warn")
        return self.get(lab_id)

    def run_checks(self, lab_id: str) -> dict:
        lab, topo = self._running(lab_id)
        self.store.log(lab_id, f"Running {len(topo.checks)} lab tests")
        results = checks.run_all(self.engine, lab_id, topo)
        run = self.store.save_check_run(lab_id, results)
        lvl = "success" if run["passed"] == run["total"] else "error"
        self.store.log(lab_id, f"Lab tests: {run['passed']}/{run['total']} passed", lvl)
        return run

    def exec(self, lab_id: str, node: str, command: str) -> dict:
        _, topo = self._running(lab_id)
        spec = self._node(topo, node)
        cmd = ["vtysh", "-c", command] if spec.kind == "router" and not command.startswith("!") \
            else ["sh", "-c", command.lstrip("!")]
        code, out = self.engine.exec(lab_id, node, cmd)
        return {"exit_code": code, "output": out}

    def show_config(self, lab_id: str, node: str) -> dict:
        _, topo = self._running(lab_id)
        spec = self._node(topo, node)
        code, out = self.engine.exec(lab_id, node, KINDS[spec.kind].show_config_cmd())
        return {"exit_code": code, "output": out, "lang": KINDS[spec.kind].config_lang}

    def apply_config(self, lab_id: str, node: str, text: str, by: str = "") -> dict:
        _, topo = self._running(lab_id)
        spec = self._node(topo, node)
        if not text.strip():
            raise LabError("configuration is empty")
        code, out = self.engine.exec(lab_id, node, KINDS[spec.kind].apply_config_cmd(text))
        lines = len([ln for ln in text.splitlines() if ln.strip()])
        if code == 0:
            self.store.log(lab_id, f"{by or 'User'} pushed {lines} config lines to {node}", "success")
        else:
            self.store.log(lab_id, f"Config push to {node} rejected: {out.strip()[-160:]}", "error")
        return {"exit_code": code, "output": out, "ok": code == 0}

    # ---- background ---------------------------------------------------------------------------------------
    def start(self) -> None:
        self.reconcile()
        self._reaper = threading.Thread(target=self._reap_loop, daemon=True, name="reaper")
        self._reaper.start()

    def stop(self) -> None:
        self._stop.set()

    def reconcile(self) -> None:
        """After a restart: fail labs that were mid-deploy and remove containers nobody owns."""
        for lab in self.store.list_labs(active_only=True):
            if lab["status"] in ("deploying", "destroying"):
                self.store.log(lab["id"], "LabForge restarted during an operation; cleaning up", "warn")
                try:
                    self.engine.destroy(lab["id"])
                except Exception:  # noqa: BLE001
                    log.exception("reconcile destroy failed")
                self.store.update_lab(lab["id"], status="failed", destroyed_at=time.time(),
                                      error="interrupted by restart")
        try:
            known = {lab["id"] for lab in self.store.list_labs(active_only=True)}
            for orphan in self.engine.lab_ids() - known:
                log.info("removing orphaned lab resources %s", orphan)
                self.engine.destroy(orphan)
        except Exception:  # noqa: BLE001
            log.exception("orphan sweep failed")

    def reap_once(self) -> list[str]:
        expired = []
        now = time.time()
        for lab in self.store.list_labs(active_only=True):
            if lab["status"] == "running" and lab["expires_at"] <= now:
                expired.append(lab["id"])
                self.destroy(lab["id"], reason="expired")
        return expired

    def _reap_loop(self) -> None:
        while not self._stop.wait(settings.reap_interval):
            try:
                self.reap_once()
            except Exception:  # noqa: BLE001
                log.exception("reaper iteration failed")


__all__ = ["LabManager", "LabError", "EngineError"]
