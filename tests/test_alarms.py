import pytest


def alarm(dev, name):
    return next((a for a in dev.alarms() if a.name == name), None)


@pytest.mark.req("SRS-004")
def test_suction_alarm_within_3s(running):
    running.cmd("INJECT suction ON")
    elapsed = running.run_until(lambda: alarm(running, "SUCTION") is not None, max_ms=3000)
    a = alarm(running, "SUCTION")
    assert a.priority == "HIGH" and a.audible
    assert elapsed <= 3000


@pytest.mark.req("SRS-004")
def test_no_suction_alarm_in_normal_operation(running):
    running.tick(60000)
    assert running.alarm_names() == []


@pytest.mark.req("SRS-005")
def test_low_flow_alarm_after_5s_and_not_before(running):
    running.cmd("INJECT occlusion ON")
    running.tick(4900)
    assert alarm(running, "LOW_FLOW") is None
    running.run_until(lambda: alarm(running, "LOW_FLOW") is not None, max_ms=1500)
    assert alarm(running, "LOW_FLOW").priority == "MEDIUM"


@pytest.mark.req("SRS-005")
def test_transient_low_flow_does_not_alarm(running):
    running.cmd("INJECT occlusion ON")
    running.tick(3000)
    running.cmd("INJECT occlusion OFF")
    running.tick(10000)
    assert alarm(running, "LOW_FLOW") is None


@pytest.mark.req("SRS-006")
@pytest.mark.parametrize("fault,name,prio", [("purge_leak", "PURGE_LOW", "MEDIUM"),
                                             ("purge_block", "PURGE_HIGH", "HIGH")])
def test_purge_pressure_alarms_after_3s(running, fault, name, prio):
    running.cmd(f"INJECT {fault} ON")
    running.tick(2900)
    assert alarm(running, name) is None
    running.tick(200)
    a = alarm(running, name)
    assert a is not None and a.priority == prio


@pytest.mark.req("SRS-007")
def test_motor_stall_raises_high_alarm_and_stops(running):
    running.cmd("INJECT stall ON")
    elapsed = running.run_until(lambda: alarm(running, "MOTOR_STALL") is not None, max_ms=1500)
    s = running.status()
    assert alarm(running, "MOTOR_STALL").priority == "HIGH"
    assert s["state"] == "ALARM_STOP" and float(s["target"]) == 0
    assert elapsed >= 1000 - 200   # the stall must persist ~1 s first (allowing for spin-down to 10%)


@pytest.mark.req("SRS-008")
def test_sensor_fault_alarm_and_flow_unavailable(running):
    running.cmd("INJECT sensor ON")
    running.tick(300)
    a = alarm(running, "SENSOR_FAULT")
    assert a is not None and a.priority == "MEDIUM"
    assert running.status()["flow"] == "NA"


@pytest.mark.req("SRS-008")
def test_sensor_fault_does_not_report_stale_flow(running):
    running.cmd("INJECT sensor ON")
    for _ in range(5):
        running.tick(100)
        assert running.status()["flow"] == "NA"


@pytest.mark.req("SRS-009")
def test_acknowledge_silences_for_120s_then_reannunciates(running):
    running.cmd("INJECT purge_leak ON")
    running.tick(3100)
    assert alarm(running, "PURGE_LOW").audible
    assert running.cmd("ACK") == "OK acked=1"
    assert not alarm(running, "PURGE_LOW").audible
    running.tick(119000)
    assert not alarm(running, "PURGE_LOW").audible
    running.tick(2000)
    assert alarm(running, "PURGE_LOW").audible


@pytest.mark.req("SRS-010")
def test_high_alarm_latches_until_acknowledged(running):
    running.cmd("INJECT suction ON")
    running.tick(3000)
    running.cmd("INJECT suction OFF")
    running.tick(10000)
    assert alarm(running, "SUCTION") is not None        # condition gone, alarm latched
    running.cmd("ACK")
    assert alarm(running, "SUCTION") is None


@pytest.mark.req("SRS-010")
def test_medium_alarm_clears_without_acknowledgement(running):
    running.cmd("INJECT purge_leak ON")
    running.tick(3100)
    running.cmd("INJECT purge_leak OFF")
    running.tick(100)
    assert alarm(running, "PURGE_LOW") is None


@pytest.mark.req("SRS-011")
def test_alarms_ordered_by_priority_then_age(running):
    running.cmd("INJECT occlusion ON")
    running.tick(7000)                    # LOW_FLOW (MEDIUM), oldest
    running.cmd("INJECT purge_leak ON")
    running.tick(3100)                    # PURGE_LOW (MEDIUM)
    running.cmd("INJECT suction ON")
    running.tick(3000)                    # SUCTION (HIGH), newest
    assert running.alarm_names() == ["SUCTION", "LOW_FLOW", "PURGE_LOW"]
