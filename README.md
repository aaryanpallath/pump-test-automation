# Blood Pump Controller — Embedded C Firmware & pytest End-to-End Test Automation

An end-to-end test automation framework for a simulated medical device: a blood pump controller written in C,
verified by a pytest suite against a written requirements specification, with requirements traceability,
generated test reports, a SQLite test history, and a defect log of real bugs the suite found.

> The controller is an educational simulation inspired by catheter-based heart pumps. It is not a medical device
> and its hemodynamic model is a test stimulus, not a clinical model.

## Overview

| | |
|---|---|
| Requirements | 14 (`requirements.yaml`) |
| Automated tests | 68, all requirement-tagged; plus 300 generated fuzz inputs per run |
| Requirements verified | 14 of 14 (`results/traceability.md`) |
| Defects found and fixed | 2 firmware defects + 1 requirement ambiguity (`DEFECTS.md`) |
| Suite run time | about 11 s against the sanitizer build |

## Architecture

```
requirements.yaml (SRS) ─────────────────────────────┐
                                                      ▼
tests/*.py ──▶ tests/device.py ──stdin/stdout──▶ build/pumpctl-san     tests/traceability.py (pytest plugin)
 (pytest,       (protocol client,                 (C11 controller,       ├─▶ results/traceability.md
  Hypothesis)    timeouts, typed helpers)          ASan + UBSan)         ├─▶ results/test_report.md
                                                                         └─▶ results/test_history.db (SQLite)
```

**Controller (`firmware/`, C11):** motor control for performance levels P0–P9; six alarms with priorities,
debounce, acknowledgement and 120 s silence, re-annunciation and HIGH-alarm latching; a timestamped event log;
a line protocol (`START`, `SET PLEVEL n`, `TICK ms`, `STATUS`, `ALARMS`, `ACK`, `INJECT fault ON|OFF`, `EVENTS`).
Built with `-Wall -Wextra -Wpedantic -Wconversion -Werror`, and separately with AddressSanitizer and
UndefinedBehaviorSanitizer for testing.

**Test framework (`tests/`, pytest):**
- `device.py` — runs the controller as a separate process and speaks its protocol, with per-command timeouts so a
  hang or crash fails fast with the transcript.
- `test_motor.py`, `test_alarms.py`, `test_events.py`, `test_protocol.py` — tests tagged
  `@pytest.mark.req("SRS-xxx")`.
- `traceability.py` — a pytest plugin that builds the traceability matrix and test report and records each run,
  result and captured device event in SQLite. `--require-coverage` fails the run if a requirement has no test.

## Setup

```bash
uv venv && uv pip install pytest hypothesis pyyaml ruff     # or pip install ...
make -C firmware                                            # builds build/pumpctl and build/pumpctl-san
```

## Usage

```bash
pytest --require-coverage                       # against the sanitizer build (default)
pytest --pumpctl build/pumpctl                  # against the release build
pytest -k suction                            # one area's tests
sqlite3 results/test_history.db "SELECT nodeid, outcome FROM test_results WHERE outcome='failed'"
```

Interactive session with the controller: `./build/pumpctl`, then type commands (`START`, `TICK 3000`, `STATUS`).

## Design decisions

- **Deterministic simulated time.** The firmware never reads a clock; `TICK` advances it. Timing requirements are
  tested to 10 ms precision, reproducibly, and a 120 s alarm-silence test runs in milliseconds.
- **Black-box, end-to-end.** Tests only use the protocol, so they verify the shipped binary's behavior rather than
  internals, and the same suite runs against release and sanitizer builds.
- **Sanitizers as a test oracle.** The `device` fixture requires a clean exit; a sanitizer report fails the test.
- **Boundaries both ways.** Each alarm is checked just before its limit (must not alarm) and just after (must alarm).
- **Property-based protocol testing.** Hypothesis checks "every input line gets exactly one response" over arbitrary
  bytes, biased toward the input buffer boundary. It found DEF-002.
- **Traceability built in.** Unknown requirement IDs in a test are a usage error; uncovered requirements can fail the
  run; every verdict is generated, not hand-written.

## Results

From `results/test_report.md` and `results/traceability.md`: 68 of 68 tests pass and 14 of 14 requirements are
verified against the sanitizer build. See `DEFECTS.md` for the defects found, including one the first version of
the fuzz test missed and how the test was improved to catch it.

## Limitations

- Host simulation of firmware; no real-time OS, hardware timers or hardware-in-the-loop.
- Simplified hemodynamics (sinusoidal pressures, linear pump curve).
- No IEC 62304 documentation beyond the SRS, test plan, traceability matrix and defect log.

## Testing

```bash
pytest --require-coverage && ruff check .
```

GitHub Actions builds both firmware configurations with gcc and runs the full suite on every push, uploading the
reports.

## Data & licensing

No external data. MIT license (see `LICENSE`).

## AI assistance disclosure

Built with help from Claude (Anthropic) via Claude Code; I reviewed, tested and verified the code, tests and results.
