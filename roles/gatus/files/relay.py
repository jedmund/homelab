#!/usr/bin/env python3
"""Relay Gatus and Komodo alerts to Discord as human-readable embeds.

Gatus POSTs the resolved alert payload to /alert; this service translates
Gatus's prettified condition syntax into plain language and forwards a
Discord embed to the operations webhook. Komodo's Custom alerter POSTs its
Alert JSON to /komodo, which gets the same embed layout. Stdlib only. It
runs behind the compose networks, so no port is published.

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
KOMODO_URL = os.environ.get("KOMODO_URL", "").rstrip("/")
KOMODO_RUNBOOK_URL = os.environ.get("KOMODO_RUNBOOK_URL", "")
PORT = int(os.environ.get("GATUS_RELAY_PORT", "8080"))

# Severity color is per state, which a static Gatus body could not carry.
STATE = {
    "TRIGGERED": {"emoji": "🔴", "word": "Down", "color": 15158332},
    "RESOLVED": {"emoji": "🟢", "word": "Recovered", "color": 3066993},
}

# Komodo alerts carry a severity rather than a two-state result. OK is the
# level of an informational alert, such as a completed auto-update.
KOMODO_LEVEL = {
    "CRITICAL": {"emoji": "🔴", "word": "Critical", "color": 15158332},
    "WARNING": {"emoji": "🟡", "word": "Warning", "color": 15844367},
    "OK": {"emoji": "🟢", "word": "OK", "color": 3066993},
}
KOMODO_RESOLVED = {"emoji": "🟢", "word": "Resolved", "color": 3066993}

# Komodo UI paths per ResourceTarget type.
KOMODO_PATHS = {
    "Server": "servers",
    "Stack": "stacks",
    "Deployment": "deployments",
    "Build": "builds",
    "Repo": "repos",
    "Procedure": "procedures",
    "Action": "actions",
    "Builder": "builders",
    "Alerter": "alerters",
    "ResourceSync": "resource-syncs",
    "Swarm": "swarms",
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


def komodo_state(value):
    """Render a Komodo stack or container state such as "running"."""
    return str(value).replace("_", " ").lower()


def komodo_where(data):
    """Name the server or swarm a stack or deployment alert came from."""
    host = data.get("server_name") or data.get("swarm_name")
    return f" on {host}" if host else ""


def komodo_error(err):
    """Pull the message out of a serialized Komodo error, if any."""
    if isinstance(err, dict):
        return err.get("error") or ""
    return str(err or "")


def komodo_details(kind, data):
    """Return (subject, description, what happened) for one Komodo alert."""
    name = data.get("name", "")
    if kind == "Test":
        return f"alerter {name}", "Test alert from Komodo.", "Test Alerter was run"
    if kind == "ServerUnreachable":
        return (
            f"{name} reachability",
            f"Komodo Core cannot reach the Periphery agent on {name}.",
            komodo_error(data.get("err")) or "no response from Periphery",
        )
    if kind == "ServerCpu":
        return f"{name} CPU", f"CPU use on {name} is high.", f"CPU at {data.get('percentage', 0):.1f}%"
    if kind == "ServerMem":
        used, total = data.get("used_gb", 0), data.get("total_gb", 0) or 1
        return (
            f"{name} memory",
            f"Memory use on {name} is high.",
            f"{100 * used / total:.1f}% used ({used:.1f} / {total:.1f} GiB)",
        )
    if kind == "ServerDisk":
        used, total = data.get("used_gb", 0), data.get("total_gb", 0) or 1
        path = str(data.get("path", ""))
        # Periphery reports the root filesystem through a file it bind-mounts.
        where = "root filesystem" if path == "/etc/hostname" else path
        return (
            f"{name} disk",
            f"Disk use on {name} crossed a Komodo threshold.",
            f"{where} at {100 * used / total:.1f}% ({used:.1f} / {total:.1f} GiB)",
        )
    if kind == "ServerVersionMismatch":
        return (
            f"{name} version",
            f"Periphery on {name} runs a different version than Core.",
            f"Periphery {data.get('server_version')}, Core {data.get('core_version')}",
        )
    if kind in ("StackStateChange", "ContainerStateChange"):
        noun = "Stack" if kind == "StackStateChange" else "Deployment"
        return (
            f"{name}",
            f"{noun} {name}{komodo_where(data)} changed state.",
            f"{komodo_state(data.get('from'))} to {komodo_state(data.get('to'))}",
        )
    if kind in ("StackImageUpdateAvailable", "DeploymentImageUpdateAvailable"):
        service = data.get("service")
        image = data.get("image", "")
        return (
            f"{name} update",
            f"A newer image is available for {name}{komodo_where(data)}.",
            f"{service}: {image}" if service else image,
        )
    if kind in ("StackAutoUpdated", "DeploymentAutoUpdated"):
        images = data.get("images") or [data.get("image", "")]
        return (
            f"{name} update",
            f"Komodo updated {name}{komodo_where(data)} automatically.",
            ", ".join(image for image in images if image),
        )
    if kind == "ResourceSyncPendingUpdates":
        return f"{name} sync", f"Resource Sync {name} has pending changes.", "review the sync preview in Komodo"
    if kind == "BuildFailed":
        version = data.get("version") or {}
        number = ".".join(str(version.get(part, 0)) for part in ("major", "minor", "patch"))
        return f"{name} build", f"Build {name} failed.", f"version {number}"
    if kind in ("RepoBuildFailed", "ProcedureFailed", "ActionFailed"):
        noun = {"RepoBuildFailed": "Repo build", "ProcedureFailed": "Procedure", "ActionFailed": "Action"}[kind]
        return f"{name}", f"{noun} {name} failed.", "the run's update log in Komodo has the details"
    if kind == "ScheduleRun":
        return f"{name} schedule", f"Scheduled run of {name}.", f"{data.get('resource_type', 'resource')} started"
    if kind == "Custom":
        return "custom", data.get("message", "Custom Komodo alert."), data.get("details") or "no details"
    return kind, f"Komodo alert {kind}.", json.dumps(data)[:900]


def build_komodo_embed(alert):
    """Build the Discord embed body for one Komodo Alert."""
    payload = alert.get("data") or {}
    kind = payload.get("type", "None")
    data = payload.get("data") or {}
    if alert.get("resolved"):
        state = KOMODO_RESOLVED
    else:
        state = KOMODO_LEVEL.get(alert.get("level", ""), KOMODO_LEVEL["WARNING"])
    subject, description, happened = komodo_details(kind, data)

    fields = [{"name": "What happened", "value": happened or "no details"}]
    target = alert.get("target") or {}
    path = KOMODO_PATHS.get(target.get("type", ""))
    if KOMODO_URL and path and target.get("id"):
        fields.append({"name": "Komodo", "value": f"{KOMODO_URL}/{path}/{target['id']}", "inline": True})
    elif KOMODO_URL:
        fields.append({"name": "Komodo", "value": KOMODO_URL, "inline": True})
    if KOMODO_RUNBOOK_URL:
        fields.append({"name": "Runbook", "value": KOMODO_RUNBOOK_URL, "inline": True})

    embed = {
        "title": f"{state['emoji']} {state['word']}: komodo/{subject}",
        "description": description,
        "color": state["color"],
        "fields": fields,
    }
    return {"embeds": [embed]}


def post_to_discord(body):
    """POST one webhook body to Discord. Returns (HTTP status, error text)."""
    request = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=json.dumps(body).encode(),
        # Discord sits behind Cloudflare, which 403s the default
        # Python-urllib user agent; identify ourselves instead.
        headers={"Content-Type": "application/json", "User-Agent": "GatusAlertRelay/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, ""
    except urllib.error.HTTPError as error:
        return None, f"discord rejected the embed: {error.code} {error.read()[:200]!r}"
    except urllib.error.URLError as error:
        return None, f"could not reach discord: {error}"


ROUTES = {
    "/alert": (build_embed, lambda payload: payload.get("state", "?")),
    "/komodo": (
        build_komodo_embed,
        lambda alert: f"komodo {(alert.get('data') or {}).get('type', '?')}",
    ),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._reply(200, b"ok")
        else:
            self._reply(404, b"not found")

    def do_POST(self):
        route = ROUTES.get(self.path)
        if route is None:
            self._reply(404, b"not found")
            return
        build, label = route
        length = min(int(self.headers.get("Content-Length", "0")), 65536)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
            body = build(payload)
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            print(f"rejected payload: {error}", flush=True)
            self._reply(400, b"bad payload")
            return
        discord_status, error = post_to_discord(body)
        if error:
            print(error, flush=True)
            self._reply(502, error.split(":")[0].encode())
            return
        print(f"delivered {label(payload)} alert to discord ({discord_status})", flush=True)
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
