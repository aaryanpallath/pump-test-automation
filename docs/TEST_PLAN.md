# Test Plan — Simulated Blood Pump Controller (SRS-PUMP v1.0)

## 1. Scope
End-to-end verification of the controller firmware (`firmware/`) against the 14 requirements in
`requirements.yaml`: motor control, performance levels, alarm detection and handling, event logging, and command
protocol robustness. Out of scope: the hemodynamic model's clinical accuracy (it is a test stimulus, not a product
feature), hardware, and timing on a real microcontroller.

## 2. Approach
- **End-to-end, black box.** Each test starts the compiled controller as its own process and drives it only through
  its command protocol, exactly as an external system would.
- **Deterministic time.** The controller has no clock; tests advance simulated time with `TICK`. Timing
  requirements (for example "within 3 s", "not before 5 s") are verified to the 10 ms tick, reproducibly, in
  milliseconds of wall time.
- **Fault injection.** `INJECT <fault> ON|OFF` creates each alarm condition: suction, occlusion, purge leak, purge
  block, motor stall, pressure sensor fault.
- **Boundary and negative tests.** Alarms are checked just before and after their debounce limits; invalid
  parameters, unknown commands and line-length limits are checked at and around each boundary.
- **Property-based fuzzing.** Hypothesis generates arbitrary byte strings (biased toward the 127-byte input buffer)
  and checks that every line gets exactly one response and the controller stays responsive.
- **Sanitizers as an oracle.** Tests run against a build with AddressSanitizer and UndefinedBehaviorSanitizer; any
  memory error or undefined behavior makes the controller exit non-zero, which fails the test even if its
  assertions passed.

## 3. Traceability
Every test declares the requirements it verifies (`@pytest.mark.req("SRS-004")`). After each run,
`results/traceability.md` lists every requirement with its tests and a verdict (PASS, FAIL, NOT COVERED).
`pytest --require-coverage` fails the run if any requirement has no test.

## 4. Environment
macOS and Ubuntu (CI), Python 3.11, pytest, Hypothesis, C11 compiler (clang or gcc) with `-Wall -Wextra -Werror`.

## 5. Entry and exit criteria
- **Entry:** the firmware builds warning-free in both release and sanitizer configurations.
- **Exit:** all tests pass, every requirement is covered and PASS, no open defect of severity High.

## 6. Defect management
Defects are recorded in `DEFECTS.md` with an ID, the requirement affected, severity, the test that found it,
root cause, fix and a regression test. Each fix must ship with a test that fails before the fix.

## 7. Reporting
Each run writes `results/test_report.md` and `results/traceability.md`, and appends the run, every test result
and every device event to `results/test_history.db` (SQLite) for trend and failure analysis.
