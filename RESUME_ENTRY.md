# Blood Pump Controller Test Automation (Pytest)
Tech: Python, pytest, Hypothesis, C, SQLite, AddressSanitizer, Git, GitHub Actions
- Built a pytest end-to-end test framework for a simulated blood pump controller written in C, driving the firmware through its command protocol with fault injection and deterministic simulated time.
- Wrote a 14-requirement specification and test plan; 68 requirement-tagged tests verify all 14, with an auto-generated traceability matrix, test reports and SQLite test history.
- Found and fixed 2 high-severity firmware defects, including a protocol desync caught by property-based fuzzing, and ran tests against sanitizer builds to catch memory errors.
