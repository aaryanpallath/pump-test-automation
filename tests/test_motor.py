import pytest

from .device import DeviceError

RPM = {1: 25000, 2: 28000, 3: 31000, 4: 33000, 5: 35000, 6: 37000, 7: 40000, 8: 43000, 9: 46000}


@pytest.mark.req("SRS-001")
@pytest.mark.parametrize("level", range(1, 10))
def test_start_reaches_level_speed_within_2s(device, level):
    device.cmd(f"SET PLEVEL {level}")
    device.cmd("START")
    elapsed = device.run_until(lambda: float(device.status()["rpm"]) >= 0.98 * RPM[level], max_ms=2000)
    assert elapsed <= 2000
    assert device.status()["state"] == "RUNNING"


@pytest.mark.req("SRS-001", "SRS-002")
def test_start_is_refused_at_p0(device):
    device.cmd("SET PLEVEL 0")
    with pytest.raises(DeviceError) as e:
        device.cmd("START")
    assert e.value.code == "E_STATE" and device.status()["state"] == "OFF"


@pytest.mark.req("SRS-002")
@pytest.mark.parametrize("level", range(0, 10))
def test_valid_levels_accepted(device, level):
    device.cmd(f"SET PLEVEL {level}")
    assert device.status()["plevel"] == str(level)


@pytest.mark.req("SRS-002")
@pytest.mark.parametrize("bad", ["-1", "10", "3.5", "abc", "", "0x3", "99999999999999999999", "+"])
def test_invalid_levels_rejected_and_level_unchanged(device, bad):
    device.cmd("SET PLEVEL 4")
    with pytest.raises(DeviceError) as e:
        device.cmd(f"SET PLEVEL {bad}".rstrip())
    assert e.value.code == "E_RANGE"
    assert device.status()["plevel"] == "4"


@pytest.mark.req("SRS-003")
def test_flow_increases_with_level(device):
    device.cmd("SET PLEVEL 1")
    device.cmd("START")
    flows = []
    for level in range(1, 10):
        device.cmd(f"SET PLEVEL {level}")
        device.tick(4000)   # settle, then whole beats
        flows.append(float(device.status()["beat_flow"]))
    assert all(b > a for a, b in zip(flows, flows[1:], strict=False)), flows


@pytest.mark.req("SRS-014")
@pytest.mark.parametrize("level", [1, 5, 9])
def test_stop_reaches_zero_within_1s(device, level):
    device.cmd(f"SET PLEVEL {level}")
    device.cmd("START")
    device.tick(3000)
    device.cmd("STOP")
    elapsed = device.run_until(lambda: float(device.status()["rpm"]) == 0, max_ms=1000)
    assert elapsed <= 1000 and device.status()["state"] == "OFF"
