"""
evasion_test_suite.py
----------------------
Fires 20 known SQL-injection / XSS payloads -- plain and obfuscated/encoded
variants -- at the /api/assistant/ask endpoint (safe: no login lockout,
no side effects) and reports whether your rule engine actually catches each
one.

WHY THIS ENDPOINT: /api/assistant/ask calls ids.scan_payload_for_sqli() and
ids.scan_payload_for_xss() directly on the input text, AND the request also
passes through the same ASGI middleware every other endpoint goes through --
so this single endpoint exercises the full rule-engine text-scanning path
without tripping brute-force/rate-limit counters.

Usage:
    python evasion_test_suite.py                 # tests localhost:8000
    python evasion_test_suite.py <base_url>       # e.g. your Render URL
"""
import sys
import time
import json
import requests

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
ENDPOINT = f"{BASE_URL}/api/assistant/ask"

# Each tuple: (label, payload, expected_to_be_caught)
# expected=True  -> a real attack payload; SHOULD be blocked
# expected=False -> a known bypass/edge-case; realistically WON'T be caught
#                   by a simple regex engine (documented limitation, not a bug)
TESTS = [
    # --- Baseline: should be caught ---
    ("SQLi: classic OR 1=1",               "' OR '1'='1", True),
    ("SQLi: UNION SELECT",                 "1 UNION SELECT username, password FROM users", True),
    ("SQLi: DROP TABLE",                   "'; DROP TABLE users; --", True),
    ("SQLi: comment truncation",           "admin'--", True),
    ("SQLi: xp_cmdshell",                  "'; EXEC xp_cmdshell('dir'); --", True),
    ("XSS: script tag",                    "<script>alert(1)</script>", True),
    ("XSS: img onerror",                   "<img src=x onerror=alert(1)>", True),
    ("XSS: javascript: protocol",          "<a href=javascript:alert(1)>click</a>", True),
    ("XSS: svg onload",                    "<svg onload=alert(1)>", True),

    # --- Case / whitespace variation: regex uses re.I, should still catch ---
    ("SQLi: mixed case OR",                "' oR '1'='1", True),
    ("XSS: mixed case script tag",         "<ScRiPt>alert(1)</ScRiPt>", True),
    ("SQLi: inline comment as space",      "' OR/**/1=1--", True),

    # --- Encoding-based evasion: realistic bypass candidates ---
    ("SQLi: URL-encoded quote+space",      "%27%20OR%20%271%27%3D%271", False),
    ("SQLi: double URL-encoded",           "%2527%2520OR%2520%25271%2527%3D%25271", False),
    ("XSS: JSON unicode-escaped <",        "\\u003cscript\\u003ealert(1)\\u003c/script\\u003e", False),
    ("XSS: HTML-entity encoded",           "&lt;script&gt;alert(1)&lt;/script&gt;", False),
    ("SQLi: null-byte prefix",             "admin%00' OR '1'='1", False),
    ("SQLi: SQL inline comment split",     "SEL/**/ECT * FROM users", False),
    ("XSS: nested tag obfuscation",        "<scr<script>ipt>alert(1)</scr</script>ipt>", False),
    ("XSS: unclosed/malformed tag",        "<img src=x onerror =alert(1)>", True),
]


def run():
    print(f"Target: {ENDPOINT}\n")
    results = []
    for label, payload, expected in TESTS:
        try:
            resp = requests.post(
                ENDPOINT,
                json={"question": payload},
                timeout=10,
            )
            caught = resp.status_code == 400
            status_str = "BLOCKED" if caught else f"ALLOWED ({resp.status_code})"
        except Exception as e:
            caught = None
            status_str = f"ERROR: {e}"

        if caught is None:
            verdict = "ERROR"
        elif caught == expected:
            verdict = "AS EXPECTED"
        elif caught and not expected:
            verdict = "CAUGHT (better than expected!)"
        else:
            verdict = "MISSED (bypass confirmed)"

        results.append((label, payload, expected, status_str, verdict))
        print(f"[{verdict:28}] {label:38} -> {status_str}")
        time.sleep(0.3)  # stay well under any rate limit

    print("\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)
    caught_count = sum(1 for *_, v in results if "CAUGHT" in v or v == "AS EXPECTED" and _[2])
    total = len(results)
    bypasses = [r for r in results if r[4] == "MISSED (bypass confirmed)"]
    print(f"Total payloads tested: {total}")
    print(f"Confirmed bypasses (attack got through): {len(bypasses)}")
    for label, payload, expected, status, verdict in bypasses:
        print(f"  - {label}: {payload!r}")

    # Write a markdown table for the report
    with open("evasion_test_report.md", "w", encoding="utf-8") as f:
        f.write("# SecureLend IDS -- Adversarial Evasion Test Report\n\n")
        f.write(f"Target: `{ENDPOINT}`\n\n")
        f.write("| # | Test | Payload | Expected | Result | Verdict |\n")
        f.write("|---|------|---------|----------|--------|--------|\n")
        for i, (label, payload, expected, status, verdict) in enumerate(results, 1):
            payload_esc = payload.replace("|", "\\|")
            f.write(f"| {i} | {label} | `{payload_esc}` | {'Block' if expected else 'Bypass expected'} | {status} | {verdict} |\n")
        f.write(f"\n**Confirmed bypasses:** {len(bypasses)} / {total}\n")
    print("\nWrote evasion_test_report.md -- ready to paste into your report.")


if __name__ == "__main__":
    run()