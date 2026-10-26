#!/usr/bin/env python3
"""The agentgateway config sends every request to tactiq-stop first.

What this guards
----------------
tactiq-stop (tactiq-attest crates/stop) is the agent's stop switch: the
gateway asks it before each tool call and it refuses while the agent is
stopped. That only holds if the gateway actually asks, on every path to a
tool. tactiq-stop checks the config itself before it starts, but only line by
line: it runs on the device and carries no YAML parser. The structural half
is checked here, with a real parser, on the file the image ships:

  - every listener of every bind has extAuthz in its own policies, so every
    route under it is covered, including routes added later;
  - no route, backend or top-level policy carries an extAuthz of its own
    (one that could point elsewhere or fail open);
  - the extAuthz targets 127.0.0.1:49318 over http, fails closed, has a
    requestTimeout of at least 3 s, sends the body with an explicit
    maxRequestBytes in 1..1048576 and allowPartialMessage false;
  - the file has no inline mappings (tactiq-stop's line check refuses them)
    and exactly one host entry, so the device-side check accepts it.

Needs: python3, PyYAML.
Run: python3 tests/agentgateway/test_extauthz_config.py
"""
import os
import re
import unittest

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONFIG = os.path.join(ROOT, "recipes-connectivity", "agentgateway-config", "files", "config.yaml")
LISTEN = "127.0.0.1:49318"
BODY_MAX = 1024 * 1024
MIN_TIMEOUT_MS = 3000


def load():
    with open(CONFIG, encoding="utf-8") as f:
        return f.read()


def duration_ms(v):
    m = re.fullmatch(r"(\d+)(ms|s)", str(v).strip())
    if not m:
        return None
    n = int(m.group(1))
    return n if m.group(2) == "ms" else n * 1000


def find_key(node, key, path=""):
    """Every (path, value) for `key` anywhere under node."""
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}/{k}"
            if k == key:
                out.append((p, v))
            out.extend(find_key(v, key, p))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.extend(find_key(v, key, f"{path}[{i}]"))
    return out


class StopCheck(unittest.TestCase):
    def setUp(self):
        self.text = load()
        self.cfg = yaml.safe_load(self.text)

    def listeners(self):
        for b in self.cfg.get("binds") or []:
            for l in b.get("listeners") or []:
                yield b, l

    def test_every_listener_carries_the_stop_check(self):
        ls = list(self.listeners())
        self.assertTrue(ls, "no listeners in the config")
        for b, l in ls:
            ea = ((l.get("policies") or {}).get("extAuthz"))
            self.assertIsInstance(ea, dict, f"listener on port {b.get('port')} has no extAuthz in its policies")

    def test_the_stop_check_is_configured_to_fail_closed(self):
        for _, l in self.listeners():
            ea = l["policies"]["extAuthz"]
            self.assertEqual(ea.get("host"), LISTEN)
            self.assertIn("http", ea.get("protocol") or {})
            self.assertEqual(ea.get("failureMode"), "deny")
            body = ea.get("includeRequestBody") or {}
            n = body.get("maxRequestBytes")
            self.assertIsInstance(n, int)
            self.assertTrue(1 <= n <= BODY_MAX, n)
            self.assertIs(body.get("allowPartialMessage"), False)
            t = (((ea.get("policies") or {}).get("http") or {}).get("requestTimeout"))
            ms = duration_ms(t)
            self.assertIsNotNone(ms, f"requestTimeout {t!r}")
            self.assertGreaterEqual(ms, MIN_TIMEOUT_MS)

    def test_no_other_extauthz_anywhere(self):
        hits = find_key(self.cfg, "extAuthz")
        expected = sum(1 for _ in self.listeners())
        self.assertEqual(len(hits), expected, [p for p, _ in hits])
        for p, _ in hits:
            self.assertRegex(p, r"^/binds\[\d+\]/listeners\[\d+\]/policies/extAuthz$")

    def test_management_listeners_are_on_loopback(self):
        cfg = self.cfg.get("config") or {}
        for key, port in (("adminAddr", 15000), ("statsAddr", 15020), ("readinessAddr", 15021)):
            self.assertEqual(cfg.get(key), f"127.0.0.1:{port}", key)

    def test_device_side_line_check_will_accept_it(self):
        code = "\n".join(l.split("#", 1)[0] for l in self.text.splitlines())
        self.assertNotIn("{", self.text, "tactiq-stop refuses inline mappings")
        hosts = re.findall(r"^\s*-?\s*host\s*:", code, re.M)
        self.assertEqual(len(hosts), 1, "tactiq-stop requires exactly one host entry")
        for key in ("extAuthz", "failureMode", "requestTimeout", "includeRequestBody",
                    "maxRequestBytes", "allowPartialMessage"):
            n = len(re.findall(rf"^\s*-?\s*{key}\s*:", code, re.M))
            self.assertEqual(n, 1, f"{key} appears {n} times")


if __name__ == "__main__":
    unittest.main()
