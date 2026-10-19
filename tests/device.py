"""Client for the controller's line protocol, running the firmware as a separate process (end-to-end)."""

from __future__ import annotations

import selectors
import subprocess
from dataclasses import dataclass
from pathlib import Path


class DeviceError(Exception):
    """The controller answered ERR."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


class DeviceTimeout(Exception):
    """No final OK/ERR line within the timeout: the controller hung, crashed or desynchronized."""


@dataclass
class Alarm:
    name: str
    priority: str
    audible: bool
    activated_at: int


class Device:
    def __init__(self, binary: Path, timeout_s: float = 5.0):
        self.proc = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, bufsize=0)
        self.timeout_s = timeout_s
        self._buf = b""
        self._sel = selectors.DefaultSelector()
        self._sel.register(self.proc.stdout, selectors.EVENT_READ)
        self.transcript: list[str] = []

    # ---------------------------------------------------------------- raw protocol
    def send_raw(self, data: bytes) -> list[str]:
        """Send bytes (must end with a newline) and return all response lines up to the final OK/ERR line."""
        self.proc.stdin.write(data)
        self.proc.stdin.flush()
        self.transcript.append(">> " + data.decode(errors="replace").rstrip("\n"))
        lines = []
        while True:
            line = self._readline()
            self.transcript.append("<< " + line)
            lines.append(line)
            if line.startswith(("OK", "ERR")):
                return lines

    def _readline(self) -> str:
        while b"\n" not in self._buf:
            if not self._sel.select(self.timeout_s):
                raise DeviceTimeout(f"no response within {self.timeout_s}s; last: {self.transcript[-3:]}")
            chunk = self.proc.stdout.read1(4096) if hasattr(self.proc.stdout, "read1") else self.proc.stdout.read(1)
            if not chunk:
                raise DeviceTimeout(f"controller exited (code {self.proc.poll()}); last: {self.transcript[-3:]}")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line.decode()

    def cmd(self, command: str) -> str:
        """Send one command; return the OK line, raise DeviceError on ERR."""
        final = self.send_raw((command + "\n").encode())[-1]
        if final.startswith("ERR"):
            _, code, *msg = final.split(" ", 2)
            raise DeviceError(code, msg[0] if msg else "")
        return final

    # ---------------------------------------------------------------- typed helpers
    def tick(self, ms: int) -> int:
        return int(self.cmd(f"TICK {ms}").split("t=")[1])

    def status(self) -> dict[str, str]:
        return dict(kv.split("=", 1) for kv in self.cmd("STATUS").split()[1:])

    def alarms(self) -> list[Alarm]:
        parts = self.cmd("ALARMS").split()[2:]
        out = []
        for p in parts:
            name, prio, sound, at = p.split(":")
            out.append(Alarm(name, prio, sound == "AUDIBLE", int(at)))
        return out

    def alarm_names(self) -> list[str]:
        return [a.name for a in self.alarms()]

    def events(self) -> list[dict[str, str]]:
        lines = self.send_raw(b"EVENTS\n")
        return [dict(kv.split("=", 1) for kv in ln[4:].split()) for ln in lines if ln.startswith("EVT ")]

    def run_until(self, predicate, max_ms: int, step_ms: int = 10) -> int:
        """Advance time in steps until predicate() is true; return elapsed ms, or raise AssertionError."""
        elapsed = 0
        while elapsed <= max_ms:
            if predicate():
                return elapsed
            self.tick(step_ms)
            elapsed += step_ms
        raise AssertionError(f"condition not met within {max_ms} ms")

    def close(self) -> tuple[int, str]:
        """Quit and return (exit code, stderr). A sanitizer report makes the exit code non-zero."""
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write(b"QUIT\n")
                self.proc.stdin.close()
            code = self.proc.wait(timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            code = -9
        return code, self.proc.stderr.read().decode(errors="replace")
