"""Launches real labs. Needs Docker: run with `pytest -m integration`."""

import os

import pytest

from labforge import catalog

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def mgr(tmp_path_factory):
    os.environ["LABFORGE_HOME"] = str(tmp_path_factory.mktemp("lf"))
    from labforge.manager import LabManager
    from labforge.store import Store
    return LabManager(store=Store(tmp_path_factory.mktemp("db") / "lf.db"))


@pytest.mark.parametrize("tid", sorted(catalog.load_all()))
def test_template_boots_and_passes_its_tests(mgr, tid):
    lab = mgr.create(tid, owner="pytest", wait=True)
    try:
        assert mgr.get(lab["id"])["status"] == "running", mgr.get(lab["id"]).get("error")
        run = mgr.run_checks(lab["id"])
        failed = [r for r in run["results"] if not r["ok"]]
        assert not failed, failed
    finally:
        mgr.destroy(lab["id"], wait=True)
    assert lab["id"] not in mgr.engine.lab_ids()
