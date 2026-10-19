import os
import subprocess
from pathlib import Path

import pytest

from .device import Device
from .traceability import Traceability

ROOT = Path(__file__).resolve().parent.parent


def pytest_addoption(parser):
    parser.addoption("--pumpctl", default=os.environ.get("PUMPCTL"),
                     help="controller binary under test (default: sanitizer build)")
    parser.addoption("--require-coverage", action="store_true", help="fail if any requirement has no test")


def pytest_configure(config):
    config._req_by_node = {}
    config._trace = Traceability(config)
    config.pluginmanager.register(config._trace, "traceability")


def pytest_collection_modifyitems(items, config):
    for item in items:
        config._req_by_node[item.nodeid] = [r for m in item.iter_markers("req") for r in m.args]


@pytest.fixture(scope="session")
def binary(pytestconfig) -> Path:
    chosen = pytestconfig.getoption("--pumpctl")
    if chosen:
        path = Path(chosen)
    else:
        subprocess.run(["make", "-C", str(ROOT / "firmware")], check=True, capture_output=True)
        path = ROOT / "build" / "pumpctl-san"
    pytestconfig._binary_name = path.name
    return path


@pytest.fixture()
def device(binary, request):
    """A fresh controller process per test. On teardown, its event log is saved to the test history and the
    process must exit cleanly: a crash or sanitizer report fails the test even if every assertion passed."""
    dev = Device(binary)
    yield dev
    try:
        request.config._trace.record_events(request.node.nodeid, dev.events())
    except Exception:  # noqa: BLE001 - the test may have left the device unresponsive; that is reported below
        pass
    code, stderr = dev.close()
    assert code == 0, f"controller exited with {code}:\n{stderr[-2000:]}"


@pytest.fixture()
def running(device):
    """Controller running at P2 with the motor at speed."""
    device.cmd("START")
    device.tick(3000)
    return device
