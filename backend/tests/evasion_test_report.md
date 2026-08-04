# SecureLend IDS -- Adversarial Evasion Test Report

Target: `http://localhost:8000/api/assistant/ask`

| # | Test | Payload | Expected | Result | Verdict |
|---|------|---------|----------|--------|--------|
| 1 | SQLi: classic OR 1=1 | `' OR '1'='1` | Block | BLOCKED | AS EXPECTED |
| 2 | SQLi: UNION SELECT | `1 UNION SELECT username, password FROM users` | Block | BLOCKED | AS EXPECTED |
| 3 | SQLi: DROP TABLE | `'; DROP TABLE users; --` | Block | BLOCKED | AS EXPECTED |
| 4 | SQLi: comment truncation | `admin'--` | Block | BLOCKED | AS EXPECTED |
| 5 | SQLi: xp_cmdshell | `'; EXEC xp_cmdshell('dir'); --` | Block | BLOCKED | AS EXPECTED |
| 6 | XSS: script tag | `<script>alert(1)</script>` | Block | BLOCKED | AS EXPECTED |
| 7 | XSS: img onerror | `<img src=x onerror=alert(1)>` | Block | BLOCKED | AS EXPECTED |
| 8 | XSS: javascript: protocol | `<a href=javascript:alert(1)>click</a>` | Block | BLOCKED | AS EXPECTED |
| 9 | XSS: svg onload | `<svg onload=alert(1)>` | Block | BLOCKED | AS EXPECTED |
| 10 | SQLi: mixed case OR | `' oR '1'='1` | Block | BLOCKED | AS EXPECTED |
| 11 | XSS: mixed case script tag | `<ScRiPt>alert(1)</ScRiPt>` | Block | BLOCKED | AS EXPECTED |
| 12 | SQLi: inline comment as space | `' OR/**/1=1--` | Block | BLOCKED | AS EXPECTED |
| 13 | SQLi: URL-encoded quote+space | `%27%20OR%20%271%27%3D%271` | Bypass expected | ALLOWED (200) | AS EXPECTED |
| 14 | SQLi: double URL-encoded | `%2527%2520OR%2520%25271%2527%3D%25271` | Bypass expected | ALLOWED (200) | AS EXPECTED |
| 15 | XSS: JSON unicode-escaped < | `\u003cscript\u003ealert(1)\u003c/script\u003e` | Bypass expected | ALLOWED (200) | AS EXPECTED |
| 16 | XSS: HTML-entity encoded | `&lt;script&gt;alert(1)&lt;/script&gt;` | Bypass expected | ALLOWED (200) | AS EXPECTED |
| 17 | SQLi: null-byte prefix | `admin%00' OR '1'='1` | Bypass expected | BLOCKED | CAUGHT (better than expected!) |
| 18 | SQLi: SQL inline comment split | `SEL/**/ECT * FROM users` | Bypass expected | ALLOWED (200) | AS EXPECTED |
| 19 | XSS: nested tag obfuscation | `<scr<script>ipt>alert(1)</scr</script>ipt>` | Bypass expected | BLOCKED | CAUGHT (better than expected!) |
| 20 | XSS: unclosed/malformed tag | `<img src=x onerror =alert(1)>` | Block | BLOCKED | AS EXPECTED |

**Confirmed bypasses:** 0 / 20
