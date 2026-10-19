# Defect Log

Defects found by the automated suite during development. Each was reproduced by a failing test before it was fixed.

| ID | Requirement | Severity | Found by | Summary | Status |
|---|---|---|---|---|---|
| DEF-001 | SRS-013 | High | `test_bad_commands_get_errors_and_device_keeps_working[QUITTER]` | Any command starting with `QUIT` shut the controller down | Fixed |
| DEF-002 | SRS-013 | High | `test_any_input_line_gets_exactly_one_response` (Hypothesis) | A long line containing a NUL byte produced two responses, desynchronizing every later command | Fixed |
| DEF-003 | SRS-013 | Low | `test_line_length_boundary` | Maximum command length was undefined; the firmware rejected 127-byte commands that fit its buffer | Requirement clarified |

## DEF-001 — Commands beginning with "QUIT" stop the controller
- **Observed:** `QUITTER` produced no response and the process exited with code 0.
- **Expected:** `ERR E_UNKNOWN`; the controller keeps running (SRS-013).
- **Root cause:** the main loop matched `strncmp(line, "QUIT", 4)`, a prefix comparison.
- **Fix:** exact match on `QUIT`.
- **Regression test:** `test_bad_commands_get_errors_and_device_keeps_working[QUITTER-E_UNKNOWN]`.

## DEF-002 — NUL byte in a long line yields two responses
- **Observed:** Hypothesis shrank a failure to 128 NUL bytes: the controller answered `ERR E_EMPTY` and then a
  second `ERR`, so the next command's caller read a stale response.
- **Expected:** exactly one response per input line (SRS-013).
- **Root cause:** input was read with `fgets` and measured with `strlen`, which stops at the first NUL. The
  over-long-line check therefore missed lines whose first 127 bytes contained a NUL, and the remainder of the line
  was parsed as a second command.
- **Fix:** read input byte by byte, track the true length, and reject NUL bytes with `ERR E_BADCHAR`.
- **Regression test:** `test_any_input_line_gets_exactly_one_response`.
- **Test-process note:** the first version of the property test did not find this defect. Hypothesis favours short
  inputs and the bug needs at least 128 bytes, and examples shared one controller so a stale response surfaced on
  the next example (reported as "flaky"). The generator now targets the buffer boundary and each example uses a
  fresh process.

## DEF-003 — Command length limit unspecified
- **Observed:** with the original `fgets` reader a 127-byte command was rejected as too long although the buffer
  holds 127 bytes.
- **Resolution:** SRS-013 now states the limit (127 bytes); `test_line_length_boundary` checks 127 (accepted) and 128
  (rejected).
