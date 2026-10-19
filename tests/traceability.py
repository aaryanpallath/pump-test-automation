"""pytest plugin: requirement traceability, test report, and test history in SQLite.

Tests declare what they verify with @pytest.mark.req("SRS-004"). After the session the plugin writes
results/traceability.md (requirement -> tests -> verdict), results/test_report.md, and appends the run,
every test result and every captured device event to results/test_history.db.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
SCHEMA = """
CREATE TABLE IF NOT EXISTS test_runs (id INTEGER PRIMARY KEY, started_at TEXT, git_sha TEXT, binary TEXT,
    passed INTEGER, failed INTEGER, skipped INTEGER, duration_s REAL);
CREATE TABLE IF NOT EXISTS test_results (run_id INTEGER REFERENCES test_runs(id), nodeid TEXT, outcome TEXT,
    duration_s REAL, requirements TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS device_events (run_id INTEGER REFERENCES test_runs(id), nodeid TEXT, t_ms INTEGER,
    type TEXT, detail TEXT);
"""


class Traceability:
    def __init__(self, config: pytest.Config):
        self.config = config
        self.reqs = yaml.safe_load((ROOT / "requirements.yaml").read_text())["requirements"]
        self.results: dict[str, dict] = {}
        self.events: list[tuple] = []
        self.started = time.time()

    def record_events(self, nodeid: str, events: list[dict[str, str]]) -> None:
        for e in events:
            detail = " ".join(f"{k}={v}" for k, v in e.items() if k not in ("t", "type"))
            self.events.append((nodeid, int(e.get("t", 0)), e.get("type", ""), detail))

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, items):
        known = {r["id"] for r in self.reqs}
        for item in items:
            for m in item.iter_markers("req"):
                unknown = set(m.args) - known
                if unknown:
                    raise pytest.UsageError(f"{item.nodeid} references unknown requirements {sorted(unknown)}")

    def pytest_runtest_logreport(self, report):
        if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
            item_reqs = self.config._req_by_node.get(report.nodeid, [])
            msg = "" if report.passed else str(report.longrepr).splitlines()[-1][:300] if report.longrepr else ""
            self.results[report.nodeid] = {"outcome": report.outcome, "duration": report.duration,
                                           "reqs": item_reqs, "message": msg}

    def pytest_sessionfinish(self, session):
        if not self.results:
            return
        RESULTS.mkdir(exist_ok=True)
        rows = []
        for r in self.reqs:
            tests = [(n, v) for n, v in self.results.items() if r["id"] in v["reqs"]]
            verdict = ("NOT COVERED" if not tests else "FAIL" if any(v["outcome"] == "failed" for _, v in tests)
                       else "PASS" if all(v["outcome"] == "passed" for _, v in tests) else "INCOMPLETE")
            rows.append((r["id"], r["text"], tests, verdict))
        counts = {k: sum(v["outcome"] == k for v in self.results.values()) for k in ("passed", "failed", "skipped")}
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                             text=True).stdout.strip() or "uncommitted"
        binary = getattr(self.config, "_binary_name", "unknown")
        duration = time.time() - self.started
        self._write_markdown(rows, counts, sha, binary, duration)
        self._write_db(counts, sha, binary, duration)
        uncovered = [rid for rid, _, _, v in rows if v == "NOT COVERED"]
        if uncovered and self.config.getoption("--require-coverage"):
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
            print(f"\nrequirements without tests: {uncovered}")

    def _write_markdown(self, rows, counts, sha, binary, duration):
        today = dt.date.today().isoformat()
        passed_reqs = sum(v == "PASS" for *_, v in rows)
        trace = ["# Requirements Traceability Matrix — SRS-PUMP v1.0", "",
                 f"Generated {today} from commit `{sha}` against `{binary}`. "
                 f"{passed_reqs} of {len(rows)} requirements verified.", "",
                 "| Requirement | Text | Tests | Verdict |", "|---|---|---|---|"]
        for rid, text, tests, verdict in rows:
            names = "<br>".join(f"`{n.split('::', 1)[1]}`" for n, _ in tests) or "—"
            trace.append(f"| {rid} | {text} | {names} | {verdict} |")
        (RESULTS / "traceability.md").write_text("\n".join(trace) + "\n")
        total = sum(counts.values())
        report = [f"# Test Report — {today}", "",
                  f"- Commit: `{sha}`  ·  Binary under test: `{binary}`  ·  Duration: {duration:.1f} s",
                  f"- Tests: {total} — {counts['passed']} passed, {counts['failed']} failed, "
                  f"{counts['skipped']} skipped",
                  f"- Requirements verified: {passed_reqs} of {len(rows)} (see `traceability.md`)",
                  f"- Device events captured: {len(self.events)}", "", "## Results by test file", "",
                  "| File | Passed | Failed | Slowest test (s) |", "|---|---|---|---|"]
        by_file: dict[str, list] = {}
        for n, v in self.results.items():
            by_file.setdefault(n.split("::")[0], []).append(v)
        for f, vs in sorted(by_file.items()):
            report.append(f"| `{f}` | {sum(v['outcome'] == 'passed' for v in vs)} | "
                          f"{sum(v['outcome'] == 'failed' for v in vs)} | {max(v['duration'] for v in vs):.2f} |")
        failures = [(n, v) for n, v in self.results.items() if v["outcome"] == "failed"]
        report += ["", "## Failures", ""] + ([f"- `{n}`: {v['message']}" for n, v in failures] or ["None."])
        (RESULTS / "test_report.md").write_text("\n".join(report) + "\n")

    def _write_db(self, counts, sha, binary, duration):
        con = sqlite3.connect(RESULTS / "test_history.db")
        with con:
            con.executescript(SCHEMA)
            cur = con.execute("INSERT INTO test_runs (started_at, git_sha, binary, passed, failed, skipped, "
                              "duration_s) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (dt.datetime.fromtimestamp(self.started).isoformat(timespec="seconds"), sha, binary,
                               counts["passed"], counts["failed"], counts["skipped"], round(duration, 2)))
            run_id = cur.lastrowid
            con.executemany("INSERT INTO test_results VALUES (?, ?, ?, ?, ?, ?)",
                            [(run_id, n, v["outcome"], round(v["duration"], 4), ",".join(v["reqs"]), v["message"])
                             for n, v in self.results.items()])
            con.executemany("INSERT INTO device_events VALUES (?, ?, ?, ?, ?)", [(run_id, *e) for e in self.events])
        con.close()
