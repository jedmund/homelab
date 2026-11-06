#!/usr/bin/env python3
"""Plan and run the repository's fast validation paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_GROUPS = {
    "1": ("musicbrainz", "prowlarr", "aurral"),
    "2": ("petlibro", "stash"),
    "3": ("line", "strudel"),
    "4": ("matrix", "backup"),
}
FIXTURE_ROLES = {role for roles in FIXTURE_GROUPS.values() for role in roles}
RESOURCE_TYPES = ("stack", "action", "alerter", "procedure", "user_group")
ZERO_SHA = "0" * 40


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=check
    )


def parse_name_status(raw: str) -> list[str]:
    """Return both sides of renames/copies from NUL-delimited git output."""
    fields = raw.split("\0")
    if fields and not fields[-1]:
        fields.pop()
    paths: list[str] = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        count = 2 if status.startswith(("R", "C")) else 1
        if index + count > len(fields):
            raise ValueError(f"Incomplete git name-status record for {status!r}")
        paths.extend(fields[index : index + count])
        index += count
    return paths


def changed_paths(base: str, head: str) -> tuple[list[str], str | None]:
    if not base or base == ZERO_SHA:
        return [], "comparison base is unavailable"
    for revision, label in ((base, "base"), (head, "head")):
        result = run_git("cat-file", "-e", f"{revision}^{{commit}}", check=False)
        if result.returncode:
            return [], f"{label} revision {revision} is unavailable"
    result = run_git(
        "diff",
        "--name-status",
        "-z",
        "--find-renames",
        f"{base}...{head}",
        check=False,
    )
    if result.returncode:
        message = result.stderr.strip() or "git could not compare the revisions"
        return [], message
    try:
        paths = parse_name_status(result.stdout)
    except ValueError as error:
        return [], str(error)
    if not paths:
        return [], "comparison produced no changed paths"
    return sorted(set(paths)), None


def is_documentation(path: str) -> bool:
    return path.endswith(".md") or path.startswith("docs/")


def classify(
    paths: list[str], *, force_full: bool = False, fallback: str | None = None
) -> dict:
    roles: set[str] = set()
    reasons: list[str] = []
    full = force_full or fallback is not None
    static = False

    if force_full:
        reasons.append("full suite explicitly requested")
    if fallback:
        reasons.append(f"safe fallback: {fallback}")

    for path in paths:
        if is_documentation(path):
            reasons.append(f"documentation: {path}")
            continue
        if path == "komodo/stacks.toml":
            reasons.append("Komodo declarations")
            continue
        if path.startswith("roles/"):
            parts = path.split("/", 2)
            role = parts[1] if len(parts) > 1 else ""
            if role in FIXTURE_ROLES:
                roles.add(role)
                static = True
                reasons.append(f"lifecycle fixture for role {role}")
            else:
                full = True
                reasons.append(f"role without a focused fixture: {role or path}")
            continue
        full = True
        reasons.append(f"shared or unclassified input: {path}")

    if full:
        static = True
        roles = set(FIXTURE_ROLES)

    groups = {
        group: [role for role in members if role in roles]
        for group, members in FIXTURE_GROUPS.items()
    }
    return {
        "version": 1,
        "full": full,
        "fast": True,
        "static": static,
        "roles": sorted(roles),
        "groups": groups,
        "paths": paths,
        "reasons": reasons or ["fast validation only"],
    }


def github_slug(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"[`*_~]", "", value).strip().lower()
    value = re.sub(r"[^\w\- ]", "", value)
    return re.sub(r"\s+", "-", value)


def markdown_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    fenced = False
    for line in text.splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        base = github_slug(match.group(1))
        if not base:
            continue
        count = counts.get(base, 0)
        counts[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def markdown_destinations(text: str) -> list[tuple[int, str]]:
    destinations: list[tuple[int, str]] = []
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
            continue
        if fenced:
            continue
        for match in re.finditer(r"!?\[[^]]*\]\(([^)]+)\)", line):
            destinations.append((number, match.group(1).strip()))
        definition = re.match(r"^\s*\[[^]]+\]:\s*(\S+)", line)
        if definition:
            destinations.append((number, definition.group(1)))
    return destinations


def normalize_destination(destination: str) -> str:
    if destination.startswith("<") and ">" in destination:
        return destination[1 : destination.index(">")]
    return destination.split(maxsplit=1)[0]


def validate_markdown(root: Path, files: list[Path]) -> list[str]:
    errors: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}
    for path in files:
        text = path.read_text(encoding="utf-8")
        for line, raw in markdown_destinations(text):
            destination = normalize_destination(raw)
            if not destination or destination.startswith("//"):
                continue
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", destination):
                continue
            target_text, separator, anchor = destination.partition("#")
            target_text = unquote(target_text)
            if target_text:
                target = (
                    root / target_text.lstrip("/")
                    if target_text.startswith("/")
                    else path.parent / target_text
                )
            else:
                target = path
            target = target.resolve()
            try:
                target.relative_to(root.resolve())
            except ValueError:
                errors.append(
                    f"{path.relative_to(root)}:{line}: "
                    f"link escapes repository: {destination}"
                )
                continue
            if not target.exists():
                errors.append(f"{path.relative_to(root)}:{line}: missing target: {destination}")
                continue
            if separator and anchor and target.is_file() and target.suffix.lower() == ".md":
                anchors = anchor_cache.setdefault(
                    target, markdown_anchors(target.read_text(encoding="utf-8"))
                )
                decoded = unquote(anchor).lower()
                if decoded not in anchors:
                    errors.append(f"{path.relative_to(root)}:{line}: missing anchor: {destination}")
    return errors


def validate_string_list(value: object, label: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{label} must be a list of strings")


def validate_komodo(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        return [f"{path.name}: {error}"]

    seen: set[tuple[str, str]] = set()
    for kind in RESOURCE_TYPES:
        resources = document.get(kind, [])
        if not isinstance(resources, list):
            errors.append(f"{kind} must be an array of tables")
            continue
        for index, resource in enumerate(resources):
            label = f"{kind}[{index}]"
            if not isinstance(resource, dict):
                errors.append(f"{label} must be a table")
                continue
            name = resource.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"{label}.name must be a non-empty string")
                continue
            identity = (kind, name)
            if identity in seen:
                errors.append(f"duplicate {kind} name: {name}")
            seen.add(identity)
            if "tags" in resource:
                validate_string_list(resource["tags"], f"{label}.tags", errors)
            if kind in {"stack", "action", "alerter", "procedure"} and not isinstance(
                resource.get("config"), dict
            ):
                errors.append(f"{label}.config must be a table")
            if kind == "stack" and isinstance(resource.get("config"), dict):
                config = resource["config"]
                for key in ("file_paths", "ignore_services"):
                    if key in config:
                        validate_string_list(config[key], f"{label}.config.{key}", errors)
                for key in ("files_on_host", "poll_for_updates", "auto_update", "send_alerts"):
                    if key in config and not isinstance(config[key], bool):
                        errors.append(f"{label}.config.{key} must be a boolean")
            if kind == "procedure" and isinstance(resource.get("config"), dict):
                stages = resource["config"].get("stage", [])
                if not isinstance(stages, list):
                    errors.append(f"{label}.config.stage must be a list of tables")
                else:
                    for stage_index, stage in enumerate(stages):
                        stage_label = f"{label}.config.stage[{stage_index}]"
                        if not isinstance(stage, dict):
                            errors.append(f"{stage_label} must be a table")
                            continue
                        executions = stage.get("executions")
                        if not isinstance(executions, list) or not all(
                            isinstance(item, dict) for item in executions
                        ):
                            errors.append(
                                f"{stage_label}.executions must be a list of tables"
                            )
                            continue
                        for execution_index, item in enumerate(executions):
                            execution_label = (
                                f"{stage_label}.executions[{execution_index}].execution"
                            )
                            execution = item.get("execution")
                            if not isinstance(execution, dict):
                                errors.append(f"{execution_label} must be a table")
                                continue
                            if not isinstance(execution.get("type"), str):
                                errors.append(f"{execution_label}.type must be a string")
                            if not isinstance(execution.get("params"), dict):
                                errors.append(f"{execution_label}.params must be a table")
            if kind == "user_group":
                validate_string_list(resource.get("users"), f"{label}.users", errors)
                permissions = resource.get("permissions")
                if not isinstance(permissions, list) or not all(
                    isinstance(item, dict) for item in permissions
                ):
                    errors.append(f"{label}.permissions must be a list of tables")
    return errors


def tracked_markdown() -> list[Path]:
    result = run_git("ls-files", "*.md")
    return [ROOT / name for name in result.stdout.splitlines() if (ROOT / name).is_file()]


def write_json(path: str | None, value: dict) -> None:
    if not path:
        return
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_dotenv(path: str | None, plan: dict) -> None:
    if not path:
        return
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"VALIDATION_FULL={'true' if plan['full'] else 'false'}",
        f"VALIDATION_STATIC={'true' if plan['static'] else 'false'}",
    ]
    for group, roles in plan["groups"].items():
        lines.append(f"VALIDATION_GROUP_{group}={','.join(roles)}")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def command_plan(args: argparse.Namespace) -> int:
    paths, fallback = changed_paths(args.base, args.head)
    plan = classify(paths, force_full=args.full, fallback=fallback)
    plan.update({"base": args.base, "head": args.head})
    write_json(args.output, plan)
    write_dotenv(args.dotenv, plan)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


def command_fast(args: argparse.Namespace) -> int:
    started = time.monotonic()
    markdown = tracked_markdown()
    errors = validate_markdown(ROOT, markdown)
    errors.extend(validate_komodo(ROOT / "komodo/stacks.toml"))
    diff_args = ["diff", "--check"]
    if args.base:
        paths, fallback = changed_paths(args.base, args.head)
        if fallback:
            errors.append(f"cannot check comparison diff: {fallback}")
        else:
            del paths
            diff_args.append(f"{args.base}...{args.head}")
    result = run_git(*diff_args, check=False)
    if result.returncode:
        errors.append(result.stdout.strip() or result.stderr.strip() or "git diff --check failed")
    report = {
        "version": 1,
        "phase": "fast",
        "duration_seconds": round(time.monotonic() - started, 3),
        "base": args.base,
        "head": args.head,
        "markdown_files": len(markdown),
        "errors": errors,
    }
    write_json(args.report, report)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"Fast validation passed: {report['markdown_files']} Markdown files, "
        "Komodo declarations, and whitespace"
    )
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="Classify changes into validation phases")
    plan.add_argument("--base", required=True)
    plan.add_argument("--head", default="HEAD")
    plan.add_argument("--output")
    plan.add_argument("--dotenv")
    plan.add_argument("--full", action="store_true")
    plan.set_defaults(handler=command_plan)
    fast = commands.add_parser(
        "fast", help="Validate documentation and Komodo declarations"
    )
    fast.add_argument("--base")
    fast.add_argument("--head", default="HEAD")
    fast.add_argument("--report")
    fast.set_defaults(handler=command_fast)
    return result


if __name__ == "__main__":
    arguments = parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
