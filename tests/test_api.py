"""API tests with a fake engine, so they run anywhere."""

import time

import pytest
from fastapi.testclient import TestClient

from labforge.api import create_app
from labforge.manager import LabManager
from labforge.store import Store


class FakeEngine:
    def __init__(self):
        self.deployed, self.destroyed = set(), []

    def ping(self):
        return {"ok": True, "version": "fake"}

    def image_present(self, ref):
        return True

    def deploy(self, lab_id, topo, logger):
        logger("fake deploy", "info")
        self.deployed.add(lab_id)
        return {"images": {}}

    def destroy(self, lab_id):
        self.destroyed.append(lab_id)
        self.deployed.discard(lab_id)
        return 1

    def lab_ids(self):
        return set(self.deployed)

    def node_states(self, lab_id):
        return {}

    def exec(self, lab_id, node, cmd):
        return 0, "ok\n"


@pytest.fixture()
def env(tmp_path):
    mgr = LabManager(engine=FakeEngine(), store=Store(tmp_path / "t.db"))
    with TestClient(create_app(mgr, start_background=False)) as client:
        yield client, mgr


def wait_status(client, lab_id, want, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        lab = client.get(f"/api/labs/{lab_id}").json()
        if lab["status"] == want:
            return lab
        time.sleep(0.05)
    raise AssertionError(f"lab never reached {want}: {lab['status']}")


def test_ui_and_catalog(env):
    client, _ = env
    assert "LabForge" in client.get("/").text
    cat = client.get("/api/catalog").json()
    assert len(cat) >= 5 and all(t["check_count"] for t in cat)


def test_lifecycle_and_stats(env):
    client, mgr = env
    r = client.post("/api/labs", json={"template": "ospf-starter", "owner": "Ana", "ttl_minutes": 30})
    assert r.status_code == 201
    lab = wait_status(client, r.json()["id"], "running")
    assert 0 < lab["remaining_seconds"] <= 1800
    assert client.post(f"/api/labs/{lab['id']}/extend", json={"minutes": 60}).json()["remaining_seconds"] > 1800
    client.delete(f"/api/labs/{lab['id']}")
    wait_status(client, lab["id"], "destroyed")
    assert lab["id"] in mgr.engine.destroyed
    stats = client.get("/api/stats").json()
    assert stats["labs_launched_30d"] == 1 and stats["engineers_30d"] == 1


def test_reaper_expires_labs(env):
    client, mgr = env
    lab_id = client.post("/api/labs", json={"template": "ospf-starter", "ttl_minutes": 5}).json()["id"]
    wait_status(client, lab_id, "running")
    mgr.store.update_lab(lab_id, expires_at=time.time() - 1)
    assert mgr.reap_once() == [lab_id]
    wait_status(client, lab_id, "expired")


def test_unknown_template_and_bad_ttl(env):
    client, _ = env
    assert client.post("/api/labs", json={"template": "nope"}).status_code == 404
    assert client.post("/api/labs", json={"template": "ospf-starter", "ttl_minutes": 10_000}).status_code == 400


def test_reconcile_removes_orphans(env):
    _, mgr = env
    mgr.engine.deployed.add("orphan1")
    mgr.reconcile()
    assert "orphan1" in mgr.engine.destroyed


def test_add_custom_template(env, tmp_path, monkeypatch):
    client, _ = env
    from labforge import settings as s
    monkeypatch.setattr(s.settings, "home", tmp_path)
    yml = """id: two-hosts
name: Two hosts
summary: Smallest possible lab
nodes:
  a: {kind: host, pos: [0, 0], interfaces: {eth1: 10.9.0.1/24}}
  b: {kind: host, pos: [200, 0], interfaces: {eth1: 10.9.0.2/24}}
links:
  - [a:eth1, b:eth1]
checks:
  - {name: a reaches b, type: ping, node: a, target: 10.9.0.2}
"""
    assert client.post("/api/catalog", json={"yaml": yml}).status_code == 201
    assert any(t["id"] == "two-hosts" for t in client.get("/api/catalog").json())
    assert client.post("/api/catalog", json={"yaml": "id: x"}).status_code == 422
