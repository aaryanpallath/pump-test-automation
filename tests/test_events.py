import pytest


@pytest.mark.req("SRS-012")
def test_state_changes_and_alarm_lifecycle_are_logged(device):
    device.events()                        # discard boot events
    device.cmd("START")
    device.tick(3000)
    device.cmd("INJECT purge_leak ON")
    device.tick(3100)
    device.cmd("ACK")
    device.cmd("INJECT purge_leak OFF")
    device.tick(100)
    device.cmd("STOP")
    ev = device.events()
    kinds = [(e["type"], e.get("id") or e.get("to") or e.get("name")) for e in ev]
    for expected in [("STATE", "RUNNING"), ("ALARM_ON", "PURGE_LOW"), ("ALARM_ACK", "PURGE_LOW"),
                     ("ALARM_OFF", "PURGE_LOW"), ("STATE", "OFF")]:
        assert expected in kinds, (expected, kinds)
    times = [int(e["t"]) for e in ev]
    assert times == sorted(times)


@pytest.mark.req("SRS-012")
def test_logged_alarm_time_matches_reported_activation(running):
    running.events()
    running.cmd("INJECT stall ON")
    running.tick(2000)
    on = next(e for e in running.events() if e["type"] == "ALARM_ON" and e["id"] == "MOTOR_STALL")
    assert int(on["t"]) == next(a.activated_at for a in running.alarms() if a.name == "MOTOR_STALL")


@pytest.mark.req("SRS-012")
def test_event_log_overflow_is_reported_not_silent(device):
    device.events()
    for i in range(300):                   # 300 level changes > 256-entry log
        device.cmd(f"SET PLEVEL {1 + i % 9}")
    final = device.send_raw(b"EVENTS\n")[-1]
    assert final.startswith("OK n=256") and "dropped=44" in final
