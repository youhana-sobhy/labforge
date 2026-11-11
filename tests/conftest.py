import pytest


def pytest_collection_modifyitems(config, items):
    if "integration" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="integration test: run with -m integration")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
