"""Command-line options live in the root conftest so pytest always registers them before parsing arguments."""

import os


def pytest_addoption(parser):
    parser.addoption("--pumpctl", default=os.environ.get("PUMPCTL"),
                     help="controller binary under test (default: sanitizer build)")
    parser.addoption("--require-coverage", action="store_true", help="fail if any requirement has no test")
