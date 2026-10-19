import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from .device import Device, DeviceError


@pytest.mark.req("SRS-013")
@pytest.mark.parametrize("line,code", [
    ("FLY", "E_UNKNOWN"), ("ping", "E_UNKNOWN"), ("PING extra", "E_UNKNOWN"), ("STATUS a b c", "E_ARGS"),
    ("TICK", "E_RANGE"), ("TICK 0", "E_RANGE"), ("TICK 5", "E_RANGE"), ("TICK -10", "E_RANGE"),
    ("TICK 1e3", "E_RANGE"), ("TICK 3600001", "E_RANGE"), ("INJECT warp ON", "E_ARGS"),
    ("INJECT suction MAYBE", "E_ARGS"), ("INJECT", "E_UNKNOWN"), ("SET SPEED 3", "E_UNKNOWN"), ("   ", "E_EMPTY"),
    ("QUITTER", "E_UNKNOWN"),
])
def test_bad_commands_get_errors_and_device_keeps_working(device, line, code):
    with pytest.raises(DeviceError) as e:
        device.cmd(line)
    assert e.value.code == code
    assert device.cmd("PING") == "OK PONG"


@pytest.mark.req("SRS-013")
@pytest.mark.parametrize("length,code", [(127, "E_UNKNOWN"), (128, "E_TOOLONG"), (5000, "E_TOOLONG")])
def test_line_length_boundary(device, length, code):
    with pytest.raises(DeviceError) as e:
        device.cmd("X" * length)
    assert e.value.code == code
    assert device.cmd("PING") == "OK PONG"


@pytest.mark.req("SRS-013")
@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.one_of(
    st.binary(max_size=300),
    # lines that straddle the 127-byte input buffer, where truncation and NUL bytes interact
    st.binary(min_size=110, max_size=160),
    st.builds(lambda head, pad: head + b"X" * pad, st.binary(max_size=8), st.integers(110, 160)),
).map(lambda b: b.replace(b"\n", b"")))
def test_any_input_line_gets_exactly_one_response(binary, data):
    """Property: every input line, whatever its bytes, produces exactly one final OK/ERR line, and the
    controller stays responsive. A second response would desynchronize every later command. Each example
    gets a fresh controller so a failure is attributed to the input that caused it."""
    dev = Device(binary, timeout_s=2.0)
    try:
        lines = dev.send_raw(data + b"\n")
        assert len([ln for ln in lines if ln.startswith(("OK", "ERR"))]) == 1
        assert dev.cmd("PING") == "OK PONG"
    finally:
        code, stderr = dev.close()
    assert code == 0, stderr[-1000:]
