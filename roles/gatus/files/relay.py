#!/usr/bin/env python3
"""Relay Gatus custom-provider alerts to Discord as human-readable embeds.

Gatus POSTs the resolved alert payload to /alert; this service translates
Gatus's prettified condition syntax into plain language and forwards a
Discord embed to the operations webhook. Stdlib only. It runs behind the
compose network, so no port is published.

Payload fields (rendered by Gatus's custom provider):
  state       "TRIGGERED" or "RESOLVED"
  group       endpoint group
  name        endpoint name
  description the endpoint alert's description
  conditions  [RESULT_CONDITIONS]; reaches this service unresolved for
              pushed host reports, which have no conditions
  errors      [RESULT_ERRORS]; request-level errors, or the pushed cause
              for host reports
"""

import json
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DISCORD_WEBHOOK_URL = os.environ["GATUS_DISCORD_WEBHOOK_URL"]
HOSTS_PING = os.environ.get("GATUS_DISCORD_HOSTS_PING", "")
HOST_GROUP = os.environ.get("GATUS_HOST_REPORT_GROUP", "hosts")
DASHBOARD_URL = os.environ.get("GATUS_DASHBOARD_URL", "")
RUNBOOK_URL = os.environ.get("GATUS_RUNBOOK_URL", "")
HOST_RUNBOOK_URL = os.environ.get("GATUS_HOST_RUNBOOK_URL", "")
PORT = int(os.environ.get("GATUS_RELAY_PORT", "8080"))

# Severity color is per state, which a static Gatus body could not carry.
STATE = {
    "TRIGGERED": {"emoji": "🔴", "word": "Down", "color": 15158332},
    "RESOLVED": {"emoji": "🟢", "word": "Recovered", "color": 3066993},
}

# Prettified failed conditions look like "[STATUS] (502) == 200": the
# placeholder, its resolved value in parentheses, the operator, and the
# expected value. Successful conditions keep their raw text.
CONDITION_RE = re.compile(
    r"^\[(?P<placeholder>[A-Z_]+)\](?:\.(?P<path>[\w.]+))?"
    r" \((?P<actual>[^)]*)\) (?P<op>==|!=|<=|>=|<|>) (?P<expected>.+)$"
)


def humanize_condition(condition):
    """Translate one prettified Gatus condition into plain language."""
    match = CONDITION_RE.match(condition.strip())
    if not match:
        return condition
    placeholder = match.group("placeholder")
    path = match.group("path")
    actual = match.group("actual")
    op = match.group("op")
    expected = match.group("expected")
    if placeholder == "STATUS":
        return f"HTTP {actual} (expected {expected})"
    if placeholder == "CONNECTED":
        if actual == "false":
            return "connection could not be established"
        return f"connection state {actual} (expected {expected})"
    if placeholder == "RESPONSE_TIME":
        return f"response time {actual}ms (expected {op} {expected}ms)"
    if placeholder == "CERTIFICATE_EXPIRATION":
        return f"certificate expires in {actual} (needs more than {expected})"
    if placeholder == "DOMAIN_EXPIRATION":
        return f"domain expires in {actual} (needs more than {expected})"
    if placeholder == "DNS_RCODE":
        return f"DNS response was {actual} (expected {expected})"
    if placeholder == "IP":
        return f"endpoint resolved to {actual} (expected {expected})"
    if path:
        return f"{path}: {actual} (expected {expected})"
    return f"{placeholder.lower()} was {actual} (expected {expected})"


def parse_conditions(raw):
    """Return [(marker, condition)] from a [RESULT_CONDITIONS] rendering.

    Pushed host reports have no conditions, so Gatus leaves the placeholder
    unresolved; treat that (and anything empty) as "no conditions".
    """
    if not raw or raw == "[RESULT_CONDITIONS]":
        return []
    return re.findall(r"([✅❌]) - `([^`]*)`", raw)


def build_embed(payload):
    """Build the Discord embed body for one relayed alert."""
    state = STATE.get(payload.get("state", ""), STATE["TRIGGERED"])
    group = payload.get("group", "")
    name = payload.get("name", "")
    description = payload.get("description", "")
    conditions = parse_conditions(payload.get("conditions", ""))
    errors = (payload.get("errors") or "").strip()
    is_hosts = group == HOST_GROUP

    fields = []
    if state["word"] == "Down":
        failed = [condition for marker, condition in conditions if marker == "❌"]
        if failed:
            human = "\n".join(humanize_condition(condition) for condition in failed)
            fields.append({"name": "What happened", "value": human})
        elif errors:
            fields.append({"name": "What happened", "value": errors})
        else:
            fields.append({
                "name": "What happened",
                "value": "the check failed; the status page has the details",
            })
    else:
        fields.append({"name": "What happened", "value": "all conditions passing"})

    runbook = HOST_RUNBOOK_URL if is_hosts else RUNBOOK_URL
    if DASHBOARD_URL:
        fields.append({"name": "Dashboard", "value": DASHBOARD_URL, "inline": True})
    if runbook:
        fields.append({"name": "Runbook", "value": runbook, "inline": True})

    embed = {
        "title": f"{state['emoji']} {state['word']}: {group}/{name}",
        "description": description,
        "color": state["color"],
        "fields": fields,
    }
    body = {"embeds": [embed]}
    if is_hosts and HOSTS_PING:
        body["content"] = HOSTS_PING
    return body


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._reply(200, b"ok")
        else:
            self._reply(404, b"not found")

    def do_POST(self):
        if self.path != "/alert":
            self._reply(404, b"not found")
            return
        length = min(int(self.headers.get("Content-Length", "0")), 65536)
        raw = self.rfile.read(length)
        try:
            body = build_embed(json.loads(raw))
        except (ValueError, TypeError, KeyError) as error:
            print(f"rejected payload: {error}", flush=True)
            self._reply(400, b"bad payload")
            return
        try:
            request = urllib.request.Request(
                DISCORD_WEBHOOK_URL,
                data=json.dumps(body).encode(),
                # Discord sits behind Cloudflare, which 403s the default
                # Python-urllib user agent; identify ourselves instead.
                headers={"Content-Type": "application/json", "User-Agent": "GatusAlertRelay/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                discord_status = response.status
        except urllib.error.HTTPError as error:
            print(f"discord rejected the embed: {error.code} {error.read()[:200]!r}", flush=True)
            self._reply(502, b"discord rejected the embed")
            return
        except urllib.error.URLError as error:
            print(f"could not reach discord: {error}", flush=True)
            self._reply(502, b"could not reach discord")
            return
        state = json.loads(raw).get("state", "?") if raw else "?"
        print(f"delivered {state} alert to discord ({discord_status})", flush=True)
        self._reply(200, b"delivered")

    def _reply(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)


if __name__ == "__main__":
    print(f"relay listening on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
