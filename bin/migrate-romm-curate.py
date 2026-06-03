#!/usr/bin/env python3
"""
Phase 3 (curate-existing) orchestrator. Runs on `nuc`.

Identifies ROMs against No-Intro/Redump dat files via `igir` (run inside an
ephemeral `node:lts-alpine` container with an NFS volume mount to gaming),
applies our curation rule in Python, and emits a decision CSV per platform.

The "what would happen" (scan) and "do it" (apply) phases are separate:
running scan never moves a file. apply consumes the decision CSV and only
performs `mv` operations.

Topology:
    gaming  192.168.1.4    NFS server, holds /Gaming/.data/
    nuc     192.168.1.6    Docker host. Runs this script.

Sync from the homelab repo:
    scp ~/Developer/Personal/homelab/bin/migrate-romm-curate.py nuc:~/curate.py
    ssh nuc "python3 ~/curate.py setup"
    ssh nuc "python3 ~/curate.py dats fetch"
    ssh nuc "python3 ~/curate.py scan SNES"
    # review ~/romm-migrate/work/decisions/SNES.csv
    ssh nuc "python3 ~/curate.py apply SNES --execute"
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Topology constants

NFS_SERVER = "192.168.1.4"
NFS_PATH = "/volume/f0d7215d-4972-486b-a8f7-9aca03a95951/.srv/.unifi-drive/Gaming/.data"
NFS_OPTS = f"addr={NFS_SERVER},rw,nfsvers=3,hard,intr"

# Apply phase: gaming has root access to the local fs. nuc's docker container
# gets root-squashed to a non-writable user on Archive/. So we ship the apply
# script over ssh to gaming and run it there.
GAMING_SSH = "root@192.168.1.4"
GAMING_DATA_PREFIX = "/srv/.unifi-drive/Gaming/.data"
CONTAINER_DATA_PREFIX = "/data"

DOCKER_VOL_DATA = "games-curate"
DOCKER_VOL_NPM = "romm-curate-npm-cache"
# Debian-based; igir's addon-zstd postinstall fails on Alpine (musl).
DOCKER_IMAGE_NODE = "node:20-slim"
DOCKER_IMAGE_ALPINE = "alpine:latest"

WORK_DIR = Path.home() / "romm-migrate" / "work"
SCANS_DIR = WORK_DIR / "scans"
DECISIONS_DIR = WORK_DIR / "decisions"
APPLIES_DIR = WORK_DIR / "applies"
LOGS_DIR = WORK_DIR / "logs"

# Platforms phase 3 curates (already populated in RomM today). GBA is
# handled separately via `nuke-gba`.
PHASE3_PLATFORMS = ["DC", "GB", "GBC", "GCN", "NDS", "PS2", "PSP", "PSX", "SNES"]

# Map our short platform name -> dat fetch metadata
@dataclass
class DatSource:
    platform: str           # "PSX"
    canonical: str          # "Sony - PlayStation"  (No-Intro / Redump system name)
    source: str             # "redump" | "no-intro"
    # libretro mirror raw URL for no-intro dats. None if not available.
    libretro_url: Optional[str] = None
    # Redump per-platform short code, used to build redump.org URLs.
    redump_code: Optional[str] = None
    # Manual fallback URL for the user if auto-fetch fails.
    manual_url: Optional[str] = None


DAT_SOURCES: Dict[str, DatSource] = {
    "DC": DatSource(
        "DC", "Sega - Dreamcast", "redump",
        redump_code="dc",
        manual_url="http://redump.org/datfile/dc/",
    ),
    "GB": DatSource(
        "GB", "Nintendo - Game Boy", "no-intro",
        libretro_url="https://raw.githubusercontent.com/libretro/libretro-database/master/dat/Nintendo%20-%20Game%20Boy.dat",
        manual_url="https://datomatic.no-intro.org/index.php?page=download",
    ),
    "GBC": DatSource(
        "GBC", "Nintendo - Game Boy Color", "no-intro",
        libretro_url="https://raw.githubusercontent.com/libretro/libretro-database/master/dat/Nintendo%20-%20Game%20Boy%20Color.dat",
        manual_url="https://datomatic.no-intro.org/index.php?page=download",
    ),
    "GCN": DatSource(
        "GCN", "Nintendo - GameCube", "redump",
        redump_code="gc",
        manual_url="http://redump.org/datfile/gc/",
    ),
    "NDS": DatSource(
        "NDS", "Nintendo - Nintendo DS", "no-intro",
        libretro_url="https://raw.githubusercontent.com/libretro/libretro-database/master/dat/Nintendo%20-%20Nintendo%20DS.dat",
        manual_url="https://datomatic.no-intro.org/index.php?page=download",
    ),
    "PS2": DatSource(
        "PS2", "Sony - PlayStation 2", "redump",
        redump_code="ps2",
        manual_url="http://redump.org/datfile/ps2/",
    ),
    "PSP": DatSource(
        "PSP", "Sony - PlayStation Portable", "redump",
        redump_code="psp",
        manual_url="http://redump.org/datfile/psp/",
    ),
    "PSX": DatSource(
        "PSX", "Sony - PlayStation", "redump",
        redump_code="psx",
        manual_url="http://redump.org/datfile/psx/",
    ),
    "SNES": DatSource(
        "SNES", "Nintendo - Super Nintendo Entertainment System", "no-intro",
        libretro_url="https://raw.githubusercontent.com/libretro/libretro-database/master/dat/Nintendo%20-%20Super%20Nintendo%20Entertainment%20System.dat",
        manual_url="https://datomatic.no-intro.org/index.php?page=download",
    ),
}


# ---------------------------------------------------------------------------
# Curation rule

DISQUALIFY_FLAGS = {
    "Demo", "Beta", "Proto", "Sample", "Kiosk", "Promo", "Test Program",
    "Trial", "Tech Demo", "Pre-Production", "Debug", "Auto Demo",
    "Possible Proto", "Program", "Trade Demo",
    # Japanese demos / trial versions
    "Taikenban", "Tentou Taikenban", "Tentou-you Taikenban",
    "Jitsuen-you Sample",
    # Kiosk variants
    "Wi-Fi Kiosk",
    # Not actually a ROM
    "Save Data",
    # Promotional (Not for Resale = NFR; demo/promo carts)
    "Not for Resale",
}
SPECIAL_KEEP_FLAGS = {"Unl", "Aftermarket", "Pirate", "Hack", "Unlicensed"}

# Regions that anchor the rule. (Multi-region tags like "USA, Europe" parse
# into a set; presence of any anchor makes a candidate "anchored".)
ANCHOR_USA = {"USA", "Canada"}
ANCHOR_JAPAN = {"Japan"}
ANCHOR_WORLD = {"World"}
ANCHOR_EUROPE = {"Europe", "Australia", "UK", "United Kingdom", "Scandinavia"}

KNOWN_REGIONS = (
    ANCHOR_USA | ANCHOR_JAPAN | ANCHOR_WORLD | ANCHOR_EUROPE | {
    "Korea", "Asia", "Brazil", "China", "Taiwan", "Germany", "France",
    "Italy", "Spain", "Sweden", "Netherlands", "Denmark", "Finland",
    "Norway", "Mexico", "Hong Kong", "Russia", "Poland", "Greece",
    "Portugal", "Ireland", "Latin America", "USSR", "Czech Republic",
    "Slovakia", "Croatia", "Romania", "Hungary", "Peru", "Argentina",
    "Chile", "Colombia", "Belgium", "India", "Switzerland",
})

LANGUAGE_CODES = {
    "En", "Fr", "De", "Es", "It", "Pt", "Nl", "Sv", "No", "Da", "Fi",
    "Ja", "Zh", "Ko", "Cs", "Pl", "Ru", "Tr", "El", "Hu", "Ro", "Hr",
    "Sk", "Sl", "Bg", "Et", "Lv", "Lt", "Uk", "Ar", "He",
    "Zh-Hans", "Zh-Hant", "En-US", "En-GB",
}

# Re-release / compilation / publisher / variant labels — neutral metadata
# that doesn't affect curation decisions but should be tracked so it doesn't
# pollute the "unknown_tags" diagnostic.
RELEASE_CONTEXT = {
    # Re-release platforms
    "Virtual Console", "Switch Online", "Switch", "Steam", "GOG", "Arcade",
    "Classic Mini", "NTSC", "PAL",
    # Re-release platforms (extras)
    "Wii U Virtual Console", "Wii Virtual Console", "3DS Virtual Console",
    # Japanese pricing / edition variants
    "Major Wave", "Shokai Genteiban", "Genteiban", "Shokai Seisanban",
    "Premium Box", "DX Pack", "Doukonban", "Microphone Doukonban",
    "PlayStation 2 the Best", "PSP the Best",
    "Controller Set", "Bonus Disc",
    # Disc protection / format variants
    "EDC",
    # Multi-platform
    "GameCube + Wii",
    # Datel music tool
    "Datel Games n' Music",
    # Re-release / compilation labels
    "Collection of Mana", "Collection of SaGa",
    "Seiken Densetsu Collection",
    "Mega Man X Legacy Collection",
    "The Cowabunga Collection", "Cowabunga Collection",
    "Castlevania Advance Collection", "Castlevania Anniversary Collection",
    "Contra Anniversary Collection", "Darius Cozmic Collection",
    "Disney Classic Games", "Capcom Town", "Capcom Classics Collection",
    "Konami Collector's Series",
    # Reproduction / repro / unlicensed publishers
    "Piko Interactive", "Retro-Bit", "Limited Run Games",
    "Strictly Limited Games", "QUByte Classics", "Columbus Circle",
    "Evercade", "Second Dimension", "The Retro Room",
    "Sachen", "Sachen-Commin", "IE Institute", "Imagineer",
    # Cartridge variants / regional collector variants
    "Competition Cart", "Enhancement Chip", "Alt", "BS",
    "Rumble Version", "All Unlocked",
    "NP",  # Nintendo Power flash cart re-release
    "Nintendo Power mail-order",
    # Retailer-exclusive editions
    "Special Edition", "Limited Edition", "Collector's Edition",
    "Limited Collector's Edition", "Game of the Year Edition",
    "Toys R Us", "Walmart", "Best Buy", "Target", "GameStop",
    # Distribution / certification
    "Online Enabled", "ESRB RP-M",
    # Saturn memory variants (1M/2M/4M/10M cart)
    "1M", "2M", "3M", "4M", "8M", "10M",
    # Cross-platform tags (GBA-GameCube link cable, etc.)
    "GameCube", "Game Disc",
    # GBA Netcard (rare peripheral)
    "Netcard",
    # Fan-translation group attribution (the file is also tagged (Japan)+(En),
    # so is_translation already fires; group name is informational).
    "Original Translation", "RCG Translation", "Super Fighter Team",
}

PAREN_RE = re.compile(r"\(([^)]+)\)")
EXT_RE = re.compile(
    r"\.(zip|chd|iso|gcz|rvz|nkit\.iso|nkit\.gcz|nsp|xci|3ds|cia|nds|gb|"
    r"gbc|gba|smc|sfc|smd|md|bin|img|cue|ngp|ngc|ws|wsc|vpk|pkg|7z|rar|"
    r"cdi|gdi|wud|wux)$",
    re.IGNORECASE,
)
DECRYPTED_RE = re.compile(r"_(decrypted|encrypted)$", re.IGNORECASE)


@dataclass
class Tags:
    regions: Set[str] = field(default_factory=set)
    languages: List[str] = field(default_factory=list)
    revision: float = 0.0           # numeric > letter (frac) > none (0)
    revision_str: str = ""
    disc: Optional[str] = None
    disqualify: Set[str] = field(default_factory=set)
    special: Set[str] = field(default_factory=set)
    is_translation: bool = False    # (Japan) + (En) ⇒ fan translation
    capabilities: Set[str] = field(default_factory=set)
    context: Set[str] = field(default_factory=set)  # release/repro context
    unknown: List[str] = field(default_factory=list)


def _match_whole_paren(raw: str, tags: Tags) -> bool:
    """Try to match the whole-paren string against single-tag patterns
    (rev, disc, capability, disqualify/special flags, etc.). Returns True if
    handled."""
    if raw in DISQUALIFY_FLAGS:
        tags.disqualify.add(raw)
        return True
    if raw in SPECIAL_KEEP_FLAGS:
        tags.special.add(raw)
        return True
    if raw in RELEASE_CONTEXT:
        tags.context.add(raw)
        return True
    m = re.match(r"^Rev (.+)$", raw)
    if m:
        rev_id = m.group(1).strip()
        try:
            v = float(int(rev_id))
            if v > tags.revision:
                tags.revision = v
                tags.revision_str = raw
        except ValueError:
            if len(rev_id) == 1 and rev_id.isalpha():
                v = (ord(rev_id.upper()) - ord("A") + 1) / 100.0
                if v > tags.revision:
                    tags.revision = v
                    tags.revision_str = raw
        return True
    if raw.startswith("Disc ") or raw.startswith("Side "):
        tags.disc = raw
        return True
    if "Enhanced" in raw or "Compatible" in raw:
        tags.capabilities.add(raw)
        return True
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return True  # date, usually paired with a Beta/Proto tag
    # Game/firmware version tags like "v1.00", "v2.01b" — informational
    if re.match(r"^v\d+\.\d+[a-z]?$", raw):
        tags.context.add(raw)
        return True
    m = re.match(r"^(Beta|Proto|Demo|Sample) \d+$", raw)
    if m:
        tags.disqualify.add(m.group(1))
        return True
    if raw in {"Uncensored", "Undub", "Translation"}:
        tags.special.add(raw)
        return True
    return False


def _try_classify_parts(parts: List[str], tags: Tags) -> bool:
    """If every comma-separated part of a paren classifies into a known
    bucket, accept and mutate `tags`. Otherwise return False so the caller
    can fall back to whole-paren matching."""
    classified = []
    for p in parts:
        if p in KNOWN_REGIONS:
            classified.append(("region", p))
        elif p in LANGUAGE_CODES:
            classified.append(("lang", p))
        elif p in RELEASE_CONTEXT:
            classified.append(("context", p))
        else:
            return False
    for kind, p in classified:
        if kind == "region":
            tags.regions.add(p)
        elif kind == "lang":
            tags.languages.append(p)
        elif kind == "context":
            tags.context.add(p)
    return True


def parse_tags(name: str) -> Tuple[str, Tags]:
    """Parse 'Final Fantasy VII (USA) (Disc 1) (Rev 1).chd' into base + Tags."""
    stem = EXT_RE.sub("", name)
    stem = DECRYPTED_RE.sub("", stem)
    first_paren = stem.find("(")
    if first_paren == -1:
        return stem.strip(), Tags()
    base = stem[:first_paren].strip()
    tags = Tags()
    for raw in PAREN_RE.findall(stem):
        raw = raw.strip()
        parts = [p.strip() for p in raw.split(",")]

        # Fast path: every comma-part is region/lang/context.
        if _try_classify_parts(parts, tags):
            continue

        # Whole-paren matches (rev, disc, capability, flags, special, etc.)
        if _match_whole_paren(raw, tags):
            continue

        # Last resort: classify each part individually. Salvages parens like
        # `(USA, Kiosk)` where one part is a region and another a disqualify
        # flag, or `(En, Cowabunga Collection)`.
        for p in parts:
            if p in KNOWN_REGIONS:
                tags.regions.add(p)
            elif p in LANGUAGE_CODES:
                tags.languages.append(p)
            elif p in RELEASE_CONTEXT:
                tags.context.add(p)
            elif p in DISQUALIFY_FLAGS:
                tags.disqualify.add(p)
            elif p in SPECIAL_KEEP_FLAGS:
                tags.special.add(p)
            else:
                tags.unknown.append(p)
    if "Japan" in tags.regions and "En" in tags.languages:
        tags.is_translation = True
    return base, tags


def region_anchors(t: Tags) -> Set[str]:
    """Categorize a Tag's regions into our anchor buckets."""
    a = set()
    if t.regions & ANCHOR_USA:
        a.add("USA")
    if t.regions & ANCHOR_JAPAN:
        a.add("JAPAN")
    if t.regions & ANCHOR_WORLD:
        a.add("WORLD")
    if t.regions & ANCHOR_EUROPE:
        a.add("EUROPE")
    if t.regions and not a:
        a.add("OTHER")
    return a


@dataclass
class Candidate:
    path: str          # relative to /data
    name: str
    base: str
    tags: Tags
    decision: str = ""
    reason: str = ""


def decide_group(group: List[Candidate]) -> None:
    """
    Mutates each Candidate's `decision` and `reason` based on group context.
    Group key = (base_name, disc); members share base + disc but differ on
    region/revision/flags.
    """
    # Step 1: disqualify Demo/Beta/Proto/etc. first.
    surviving: List[Candidate] = []
    for c in group:
        if c.tags.disqualify:
            c.decision = "trim"
            c.reason = f"disqualify:{','.join(sorted(c.tags.disqualify))}"
        else:
            surviving.append(c)

    # Step 2: revision dedup within same region-anchor signature.
    by_region: Dict[Tuple[str, ...], List[Candidate]] = defaultdict(list)
    for c in surviving:
        a = region_anchors(c.tags)
        key = tuple(sorted(a)) if a else ("UNTAGGED",)
        by_region[key].append(c)

    rev_winners: List[Candidate] = []
    for key, members in by_region.items():
        max_rev = max(c.tags.revision for c in members)
        for c in members:
            if c.tags.revision >= max_rev:
                rev_winners.append(c)
            else:
                c.decision = "trim"
                c.reason = f"older-rev (kept {max_rev})"

    # Step 3: region rule across the rev winners.
    has_usa = any("USA" in region_anchors(c.tags) for c in rev_winners)
    has_world = any("WORLD" in region_anchors(c.tags) for c in rev_winners)
    has_japan = any("JAPAN" in region_anchors(c.tags) for c in rev_winners)
    has_anglo = has_usa or has_world  # English-playable

    for c in rev_winners:
        a = region_anchors(c.tags)

        if c.tags.special:
            c.decision = "keep"
            c.reason = f"special:{','.join(sorted(c.tags.special))}"
            continue
        if c.tags.is_translation:
            c.decision = "keep"
            c.reason = "fan-translation"
            continue
        if "USA" in a:
            c.decision = "keep"
            c.reason = "USA"
            continue
        if "JAPAN" in a:
            c.decision = "keep"
            c.reason = "Japan"
            continue
        if "WORLD" in a:
            c.decision = "keep"
            c.reason = "World"
            continue
        if "EUROPE" in a or (not c.tags.regions and c.tags.languages):
            if has_anglo:
                c.decision = "trim"
                c.reason = "EU dropped (USA/World exists)"
            else:
                c.decision = "keep"
                c.reason = "EU fallback (no USA/World)"
            continue
        if "OTHER" in a:
            if has_anglo or has_japan:
                c.decision = "trim"
                c.reason = f"other-region dropped ({','.join(sorted(c.tags.regions))})"
            else:
                c.decision = "keep"
                c.reason = f"other-region sole copy ({','.join(sorted(c.tags.regions))})"
            continue
        # Untagged
        c.decision = "keep"
        c.reason = "untagged (no region/lang)"


# ---------------------------------------------------------------------------
# Docker helpers


def docker(*args: str) -> Tuple[int, str, str]:
    """Run docker, return (returncode, stdout, stderr)."""
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def docker_check(*args: str) -> str:
    """Run docker; on failure print stderr+stdout and raise. Returns stdout."""
    rc, out, err = docker(*args)
    if rc != 0:
        sys.stderr.write(f"docker {' '.join(args)!r} exited {rc}\n")
        if err:
            sys.stderr.write(f"--- stderr ---\n{err}\n")
        if out:
            sys.stderr.write(f"--- stdout ---\n{out}\n")
        raise subprocess.CalledProcessError(rc, ["docker", *args], out, err)
    return out


def docker_run_alpine(script: str, *, mount_data: bool = True,
                      mount_work: bool = True) -> str:
    """Run a shell snippet inside a one-shot alpine container (captured)."""
    args = ["run", "--rm"]
    if mount_data:
        args += ["-v", f"{DOCKER_VOL_DATA}:/data"]
    if mount_work:
        args += ["-v", f"{WORK_DIR}:/work"]
    args += [DOCKER_IMAGE_ALPINE, "sh", "-c", script]
    return docker_check(*args)


def docker_run_node_streaming(script: str) -> int:
    """Run a shell snippet inside the node container, streaming stdout/stderr
    live to the user's terminal. Returns exit code."""
    args = [
        "docker", "run", "--rm",
        "-v", f"{DOCKER_VOL_DATA}:/data",
        "-v", f"{WORK_DIR}:/work",
        "-v", f"{DOCKER_VOL_NPM}:/root/.npm",
        DOCKER_IMAGE_NODE, "sh", "-c", script,
    ]
    return subprocess.run(args).returncode


# ---------------------------------------------------------------------------
# Subcommands


def cmd_setup(args) -> int:
    """Create the docker volumes (idempotent)."""
    if DOCKER_VOL_DATA not in existing:
        docker_check(
            "volume", "create",
            "--driver", "local",
            "--opt", "type=nfs",
            "--opt", f"o={NFS_OPTS}",
            "--opt", f"device=:{NFS_PATH}",
            DOCKER_VOL_DATA,
        )
        print(f"created docker volume {DOCKER_VOL_DATA}")
    else:
        print(f"docker volume {DOCKER_VOL_DATA} already exists")

    if DOCKER_VOL_NPM not in existing:
        docker_check("volume", "create", DOCKER_VOL_NPM)
        print(f"created docker volume {DOCKER_VOL_NPM}")
    else:
        print(f"docker volume {DOCKER_VOL_NPM} already exists")

    for d in [WORK_DIR, SCANS_DIR, DECISIONS_DIR, APPLIES_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    print(f"work dir: {WORK_DIR}")

    # Smoke test: list /data/dats
    out = docker_run_alpine("ls /data/dats 2>&1 | head", mount_work=False)
    print("--- /data/dats ---")
    print(out)
    return 0


def cmd_teardown(args) -> int:
    """Remove the docker volumes & cached image."""
    for vol in [DOCKER_VOL_DATA, DOCKER_VOL_NPM]:
        rc, _, err = docker("volume", "rm", vol)
        if rc == 0:
            print(f"removed {vol}")
        else:
            print(f"could not remove {vol}: {err.strip()}")
    print(f"(image removal: docker image rm {DOCKER_IMAGE_NODE} {DOCKER_IMAGE_ALPINE})")
    return 0


def _dat_matches(canonical: str, filename: str) -> bool:
    """A dat filename matches a canonical platform name iff the canonical
    name is followed by ` (`, ` -`, or `.dat` (so 'Nintendo - Game Boy' does
    not match 'Nintendo - Game Boy Advance ...')."""
    if not filename.startswith(canonical):
        return False
    rest = filename[len(canonical):]
    return rest.startswith(" (") or rest.startswith(" -") or rest == ".dat"


def cmd_dats_list(args) -> int:
    """Show present vs missing dats."""
    out = docker_run_alpine("ls -1 /data/dats 2>/dev/null", mount_work=False)
    have = set(line.strip() for line in out.splitlines() if line.strip()
               and not line.startswith("@"))
    print(f"=== dats present in /Gaming/.data/dats/ ({len(have)}) ===")
    for d in sorted(have):
        print(f"  {d}")
    print()
    print("=== coverage for phase 3 platforms ===")
    for plat in PHASE3_PLATFORMS:
        src = DAT_SOURCES.get(plat)
        if not src:
            print(f"  {plat:5}  (no DatSource defined)")
            continue
        match = [d for d in have if _dat_matches(src.canonical, d)]
        status = "OK" if match else "MISSING"
        sample = match[0] if match else "—"
        print(f"  {plat:5}  {status:8}  {src.canonical:50}  {sample}")
    return 0


def cmd_dats_fetch(args) -> int:
    """Auto-fetch missing dats. Best-effort; prints manual URLs for failures."""
    out = docker_run_alpine("ls -1 /data/dats 2>/dev/null", mount_work=False)
    have = set(line.strip() for line in out.splitlines() if line.strip())

    failed: List[Tuple[str, str]] = []  # (platform, manual_url)
    fetched = 0
    for plat in PHASE3_PLATFORMS:
        src = DAT_SOURCES.get(plat)
        if not src:
            continue
        if any(src.canonical in d for d in have):
            print(f"[{plat}] already have {src.canonical}*")
            continue
        url = src.libretro_url
        if not url and src.source == "redump":
            # Redump has a JS-driven download form; skip auto for now.
            url = None
        if not url:
            print(f"[{plat}] no auto source; fetch manually: {src.manual_url}")
            failed.append((plat, src.manual_url or ""))
            continue
        # Fetch via wget inside alpine, write directly to /data/dats/.
        target_name = f"{src.canonical}.dat"
        target_path = f"/data/dats/{target_name}"
        cmd = (
            f"set -e; "
            f"apk add --no-cache wget >/dev/null 2>&1 || true; "
            f"wget -qO '{target_path}.tmp' '{url}' && "
            f"mv '{target_path}.tmp' '{target_path}' && "
            f"echo OK"
        )
        try:
            result = docker_run_alpine(cmd, mount_work=False)
            if "OK" in result:
                print(f"[{plat}] fetched {target_name}")
                fetched += 1
            else:
                print(f"[{plat}] fetch failed: {result.strip()}")
                failed.append((plat, src.manual_url or ""))
        except subprocess.CalledProcessError as e:
            print(f"[{plat}] fetch errored: {e}")
            failed.append((plat, src.manual_url or ""))

    print()
    print(f"=== summary: fetched {fetched}, manual {len(failed)} ===")
    if failed:
        print("Fetch these manually and drop into /Gaming/.data/dats/:")
        for plat, url in failed:
            print(f"  {plat}: {url}")
    return 0 if not failed else 1


def cmd_scan(args) -> int:
    """Scan one platform: igir report + apply rule + emit decision CSV."""
    plat = args.platform.upper()
    if plat not in PHASE3_PLATFORMS:
        print(f"ERROR: {plat} is not in phase 3 scope ({PHASE3_PLATFORMS})",
              file=sys.stderr)
        return 2

    src = DAT_SOURCES[plat]

    if args.reuse_scan:
        candidates = sorted(SCANS_DIR.glob(f"{plat}-igir-*.csv"))
        if not candidates:
            print(f"ERROR: --reuse-scan but no prior scan in {SCANS_DIR}",
                  file=sys.stderr)
            return 4
        igir_csv = candidates[-1]
        print(f">>> reusing existing igir CSV: {igir_csv}")
    else:
        timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        igir_csv = SCANS_DIR / f"{plat}-igir-{timestamp}.csv"
        # --input-checksum-archives never: don't crack open archives (zip/chd)
        # to inspect their contents. We curate by filename, not by ROM hash,
        # so dat-matching contents adds nothing for our purpose. Without this
        # flag igir spent ~60 min decompressing CHDs to /tmp for DC.
        igir_args = (
            f"npx -y igir@latest report "
            f"-d /data/dats/ "
            f"-i '/data/RomM/library/roms/{plat}/' "
            f"--report-output '/work/scans/{plat}-igir-{timestamp}.csv' "
            f"--input-checksum-min CRC32 --input-checksum-max SHA256 "
            f"--input-checksum-archives never"
        )
        print(f">>> running igir for {plat} (this hashes every file; may take a while)")
        print(f"    cmd: {igir_args}")
        rc = docker_run_node_streaming(igir_args)
        if rc != 0:
            print(f"igir exited {rc}", file=sys.stderr)
            return 3
        if not igir_csv.exists():
            candidates = sorted(SCANS_DIR.glob(f"{plat}-igir-*.csv"))
            if not candidates:
                print(f"ERROR: igir did not produce a CSV", file=sys.stderr)
                return 4
            igir_csv = candidates[-1]

    # --- parse igir CSV, build candidates, apply rule ---
    candidates = build_candidates_from_igir(igir_csv, plat, src)

    # Group by (base, disc) and decide
    groups: Dict[Tuple[str, Optional[str]], List[Candidate]] = defaultdict(list)
    for c in candidates:
        groups[(c.base, c.tags.disc)].append(c)
    for group in groups.values():
        decide_group(group)

    # --- write decision CSV ---
    decision_path = DECISIONS_DIR / f"{plat}.csv"
    with decision_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "decision", "reason", "path", "base", "regions", "revision",
            "disc", "flags", "languages", "context", "unknown_tags",
        ])
        for c in sorted(candidates, key=lambda c: (c.decision, c.base, c.path)):
            w.writerow([
                c.decision, c.reason, c.path, c.base,
                ",".join(sorted(c.tags.regions)),
                c.tags.revision_str or "",
                c.tags.disc or "",
                ",".join(sorted(c.tags.disqualify | c.tags.special)),
                ",".join(c.tags.languages),
                ",".join(sorted(c.tags.context)),
                ",".join(c.tags.unknown),
            ])

    # --- summary ---
    by_decision: Dict[str, int] = defaultdict(int)
    by_reason: Dict[str, int] = defaultdict(int)
    for c in candidates:
        by_decision[c.decision] += 1
        by_reason[c.reason] += 1
    print(f"=== {plat} scan summary ===")
    print(f"total files:        {len(candidates)}")
    for d, n in sorted(by_decision.items()):
        print(f"  {d:<10}  {n}")
    print()
    print("top reasons:")
    for r, n in sorted(by_reason.items(), key=lambda x: -x[1])[:15]:
        print(f"  {n:>6}  {r}")
    print()
    print(f"decision CSV: {decision_path}")
    print(f"igir CSV:     {igir_csv}")
    return 0


def build_candidates_from_igir(igir_csv: Path, plat: str,
                               src: DatSource) -> List[Candidate]:
    """
    Parse igir's CSV. Each row is one game-vs-dat result; we want one
    Candidate per file present in the source dir.
    igir columns (from prior runs):
      DAT Name, Game Name, Status, ROM Files, Patched, BIOS, Retail Release,
      Unlicensed, Debug, Demo, Beta, Sample, Prototype, Program, Aftermarket,
      Homebrew, Bad
    Status values: FOUND (file matches dat), MISSING (game in dat but no file),
                   UNUSED (file present but not in dat).
    """
    candidates: List[Candidate] = []
    seen_paths: Set[str] = set()
    with igir_csv.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = row.get("Status", "").strip()
            game_name = row.get("Game Name", "").strip()
            rom_files = row.get("ROM Files", "").strip()
            if status == "MISSING":
                continue  # game in dat but no file we have
            if not rom_files:
                continue
            # ROM Files can be a |-separated list in the igir CSV.
            for path in rom_files.split("|"):
                path = path.strip()
                if not path or path in seen_paths:
                    continue
                seen_paths.add(path)
                # Use the dat-canonical Game Name when matched (UNUSED rows
                # have no game name; fall back to filename).
                source_name = game_name if status == "FOUND" else Path(path).name
                base, tags = parse_tags(source_name)
                # igir flags: convert "true"/"false" columns into our tags
                if row.get("Demo", "").lower() == "true":
                    tags.disqualify.add("Demo")
                if row.get("Beta", "").lower() == "true":
                    tags.disqualify.add("Beta")
                if row.get("Sample", "").lower() == "true":
                    tags.disqualify.add("Sample")
                if row.get("Prototype", "").lower() == "true":
                    tags.disqualify.add("Proto")
                if row.get("Program", "").lower() == "true":
                    tags.disqualify.add("Test Program")
                if row.get("Debug", "").lower() == "true":
                    tags.disqualify.add("Debug")
                if row.get("Unlicensed", "").lower() == "true":
                    tags.special.add("Unl")
                if row.get("Aftermarket", "").lower() == "true":
                    tags.special.add("Aftermarket")
                # status=UNUSED → file matched no dat entry. Could be UNDUB,
                # personal patch, or scene-pack. We default to keeping these.
                candidates.append(Candidate(
                    path=path, name=Path(path).name,
                    base=base, tags=tags,
                ))
                if status == "UNUSED":
                    # Mark in reason later via decide_group if it goes
                    # through; but we want to ensure unmatched files default
                    # to keep with a clear reason if no group context.
                    pass
    return candidates


def _translate_to_gaming(path: str) -> str:
    """Convert an in-container path (/data/...) to gaming-native (/srv/...)."""
    if path.startswith(CONTAINER_DATA_PREFIX + "/"):
        return GAMING_DATA_PREFIX + path[len(CONTAINER_DATA_PREFIX):]
    return path


def cmd_apply(args) -> int:
    """Read decision CSV and perform mv operations on gaming via ssh.

    nuc's docker container can't write into /data/Archive (NFS root-squashed
    to a read-only user). Instead we generate a shell script with gaming-
    native paths and pipe it to `ssh root@gaming bash`.
    """
    plat = args.platform.upper()
    decision_path = DECISIONS_DIR / f"{plat}.csv"
    if not decision_path.exists():
        print(f"ERROR: no decision CSV at {decision_path}; run `scan {plat}` first",
              file=sys.stderr)
        return 2

    moves: List[Tuple[str, str]] = []  # (src, dst) in gaming-native paths
    with decision_path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["decision"] != "trim":
                continue
            src = _translate_to_gaming(row["path"])
            basename = Path(src).name
            dst = f"{GAMING_DATA_PREFIX}/Archive/Curated-Trimmed/{plat}/{basename}"
            moves.append((src, dst))

    print(f"=== apply {plat}: {len(moves)} files would move ===")
    if not args.execute:
        for s, d in moves[:10]:
            print(f"  MV  {s} -> {d}")
        if len(moves) > 10:
            print(f"  ... and {len(moves) - 10} more (rerun with --execute)")
        return 0

    # Build the shell script content. Each mv is guarded by `[ -e $src ]` so
    # that re-applying a CSV after some moves already happened doesn't error
    # out (idempotent).
    lines = ["#!/bin/sh"]
    lines.append(f"mkdir -p '{GAMING_DATA_PREFIX}/Archive/Curated-Trimmed/{plat}'")
    lines.append("moved=0; skipped=0")
    for s, d in moves:
        sq = s.replace("'", "'\\''")
        dq = d.replace("'", "'\\''")
        lines.append(
            f"if [ -e '{sq}' ]; then mv -n -- '{sq}' '{dq}' && moved=$((moved+1)); "
            f"else skipped=$((skipped+1)); fi"
        )
    lines.append(f"echo \"DONE: {plat} moved=$moved skipped=$skipped (total in csv: {len(moves)})\"")
    script = "\n".join(lines) + "\n"

    # Save a copy locally for the audit trail.
    apply_script = APPLIES_DIR / f"{plat}.sh"
    apply_script.write_text(script)

    if args.emit_script:
        sys.stdout.write(script)
        return 0

    # Pipe to ssh root@gaming bash.
    print(f"piping {len(moves)} mv ops to {GAMING_SSH} ...")
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", GAMING_SSH, "bash"],
            input=script, text=True, capture_output=True,
        )
    except FileNotFoundError:
        print("ssh not available on this host", file=sys.stderr)
        return 5
    print(result.stdout, end="")
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.returncode != 0:
        print(f"ssh apply failed (rc={result.returncode}). Script saved at "
              f"{apply_script}; you can run it manually:", file=sys.stderr)
        print(f"  ssh {GAMING_SSH} bash < {apply_script}", file=sys.stderr)
        return result.returncode
    return 0


def cmd_nuke_gba(args) -> int:
    """Move every file under RomM/library/roms/GBA/ to Archive/Curated-Trimmed/GBA-scene/."""
    target = "/data/Archive/Curated-Trimmed/GBA-scene"
    print(f">>> nuke-gba: clearing /data/RomM/library/roms/GBA/ -> {target}")
    if not args.execute:
        out = docker_run_alpine(
            f"ls /data/RomM/library/roms/GBA 2>&1 | head -20; "
            f"echo ---; "
            f"find /data/RomM/library/roms/GBA -mindepth 1 -maxdepth 1 | wc -l",
            mount_work=False,
        )
        print(out)
        print("(rerun with --execute to perform the move)")
        return 0
    out = docker_run_alpine(
        f"set -e; "
        f"mkdir -p '{target}'; "
        f"find /data/RomM/library/roms/GBA -mindepth 1 -maxdepth 1 "
        f"  ! -name '@eaDir' -exec mv -n -t '{target}/' {{}} +; "
        f"echo DONE",
        mount_work=False,
    )
    print(out)
    return 0


# ---------------------------------------------------------------------------
# Phase 4: hard-link curated subsets from Archive/Myrient/ into RomM platform
# dirs. Source files stay in place; RomM gets a hard-link view of the keep set.
# Idempotent: running apply twice is safe (skips already-linked files).


@dataclass
class Phase4Unit:
    short: str                                  # "GBA", "3DS-Digital", "PSV-Updates"
    dest: str                                   # path under RomM/library/roms/
    sources: List[str]                          # paths relative to Archive/Myrient
    depends_on: List[str] = field(default_factory=list)
    filter_fn: Optional[str] = None


PHASE4_UNITS: Dict[str, Phase4Unit] = {
    # Single-source, simple
    "GBA":  Phase4Unit("GBA",  "GBA",  ["No-Intro/Nintendo - Game Boy Advance"]),
    "GEN":  Phase4Unit("GEN",  "GEN",  ["Loose/Genesis"]),
    "SMS":  Phase4Unit("SMS",  "SMS",  ["Loose/MasterSystem"]),
    "GG":   Phase4Unit("GG",   "GG",   ["Loose/GameGear"]),
    "NGP":  Phase4Unit("NGP",  "NGP",  ["No-Intro/SNK - NeoGeo Pocket"]),
    "NGPC": Phase4Unit("NGPC", "NGPC", ["No-Intro/SNK - NeoGeo Pocket Color"]),
    "WS":   Phase4Unit("WS",   "WS",   ["No-Intro/Bandai - WonderSwan"]),
    "GDC":  Phase4Unit("GDC",  "GDC",  ["No-Intro/Tiger - Game.com"]),
    "PIP":  Phase4Unit("PIP",  "PIP",  ["Redump/Bandai - Pippin"]),
    "WII":  Phase4Unit("WII",  "WII",  ["Redump/Nintendo - Wii - NKit RVZ [zstd-19-128k]"]),
    "WIIU": Phase4Unit("WIIU", "WIIU", ["Redump/Nintendo - Wii U - WUX"]),
    "XBOX": Phase4Unit("XBOX", "XBOX", ["Redump/Microsoft - Xbox"]),
    "NGCD": Phase4Unit("NGCD", "NGCD", ["Redump/SNK - Neo Geo CD"]),
    "SCD":  Phase4Unit("SCD",  "SCD",  ["Redump/Sega - Mega CD & Sega CD"]),
    "SAT":  Phase4Unit("SAT",  "SAT",  ["Redump/Sega - Saturn"]),
    "PSV":  Phase4Unit("PSV",  "PSV",  ["Loose/PSVita-Content"]),
    # Multi-source
    "N64":  Phase4Unit("N64",  "N64",
        ["Loose/N64", "No-Intro/Nintendo - Nintendo 64DD"]),
    "WSC":  Phase4Unit("WSC",  "WSC",
        ["No-Intro/Bandai - WonderSwan Color",
         "No-Intro/Bandai - WonderSwan Color (Aftermarket)"]),
    "VB":   Phase4Unit("VB",   "VB",
        ["No-Intro/Nintendo - Virtual Boy",
         "No-Intro/Nintendo - Virtual Boy (Aftermarket)",
         "No-Intro/Nintendo - Virtual Boy (Private)"]),
    "PD":   Phase4Unit("PD",   "PD",
        ["No-Intro/Panic - Playdate (Catalog) (Decrypted)",
         "No-Intro/Panic - Playdate (Various)",
         "No-Intro/Panic - Playdate (itch.io)"]),
    # 3DS layout (designed so RomM doesn't trip on mixed encrypted/decrypted/digital):
    #   RomM/library/roms/3DS/        = decrypted cart .3ds files only
    #   RomM/library/roms/3DS-eShop/  = eShop-exclusive Digital .cia files
    # 3DS-Encrypted is not surfaced in RomM (kept in Archive/Myrient/ only).
    "3DS-Decrypted": Phase4Unit("3DS-Decrypted", "3DS",
        ["No-Intro/Nintendo - Nintendo 3DS (Decrypted)",
         "No-Intro/Nintendo - New Nintendo 3DS (Decrypted)"]),
    "3DS-Digital": Phase4Unit("3DS-Digital", "3DS-eShop",
        ["No-Intro/Nintendo - Nintendo 3DS (Digital) (CDN)",
         "No-Intro/Nintendo - Nintendo 3DS (Digital) (SpotPass)"],
        depends_on=["3DS-Decrypted"],
        filter_fn="eshop_exclusive_only"),
    "PSV-Updates": Phase4Unit("PSV-Updates", "PSV-Updates",
        ["Loose/PSVita-Updates"],
        depends_on=["PSV"],
        filter_fn="matching_games_only"),
}


def _phase4_decision_path(short: str) -> Path:
    return DECISIONS_DIR / f"phase4-{short}.csv"


def _phase4_list_source_files(unit: Phase4Unit) -> List[str]:
    """Return absolute /data-prefixed paths of every file in unit.sources."""
    src_args = " ".join(
        f"'{GAMING_DATA_PREFIX}/Archive/Myrient/{s}'" for s in unit.sources
    )
    cmd = (
        f"for d in {src_args}; do "
        f"  [ -d \"$d\" ] && find \"$d\" -maxdepth 1 -mindepth 1 ! -name '@eaDir' -type f"
        f"; done"
    )
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", GAMING_SSH, cmd],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ssh listing failed: {result.stderr}")
    paths = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    # Translate to /data prefix for consistency with phase 3 CSVs.
    return [
        p.replace(GAMING_DATA_PREFIX, CONTAINER_DATA_PREFIX, 1)
        for p in paths
    ]


def _phase4_load_keep_bases(short: str) -> Set[str]:
    """Read decision CSV for `short` and return the set of base names kept."""
    path = _phase4_decision_path(short)
    bases: Set[str] = set()
    with path.open() as f:
        for r in csv.DictReader(f):
            if r["decision"] == "keep":
                bases.add(r["base"])
    return bases


def cmd_phase4_scan(args) -> int:
    """Scan Myrient sources for a phase 4 unit; emit decision CSV; no moves."""
    short = args.platform
    if short not in PHASE4_UNITS:
        print(f"unknown phase 4 unit: {short}", file=sys.stderr)
        print(f"available: {', '.join(PHASE4_UNITS)}", file=sys.stderr)
        return 2
    unit = PHASE4_UNITS[short]

    # Verify dependencies if any.
    for dep in unit.depends_on:
        if not _phase4_decision_path(dep).exists():
            print(f"ERROR: {short} depends on {dep}; run `phase4-scan {dep}` first",
                  file=sys.stderr)
            return 3

    # Source listing via ssh.
    print(f">>> listing sources for {short} (over ssh to gaming)")
    paths = _phase4_list_source_files(unit)
    print(f"    {len(paths)} files across {len(unit.sources)} source dirs")

    # Build candidates.
    candidates: List[Candidate] = []
    for p in paths:
        name = Path(p).name
        base, tags = parse_tags(name)
        candidates.append(Candidate(path=p, name=name, base=base, tags=tags))

    # Pre-filter via dep decisions.
    if unit.filter_fn == "eshop_exclusive_only":
        cart_bases: Set[str] = set()
        for dep in unit.depends_on:
            cart_bases |= _phase4_load_keep_bases(dep)
        before = len(candidates)
        candidates = [c for c in candidates if c.base not in cart_bases]
        print(f"    eshop-exclusive filter: dropped {before - len(candidates)} "
              f"(have cart equivalents in {','.join(unit.depends_on)})")
    elif unit.filter_fn == "matching_games_only":
        keep_bases: Set[str] = set()
        for dep in unit.depends_on:
            keep_bases |= _phase4_load_keep_bases(dep)
        before = len(candidates)
        candidates = [c for c in candidates if c.base in keep_bases]
        print(f"    matching-games filter: dropped {before - len(candidates)} "
              f"(no curated game in {','.join(unit.depends_on)})")

    # Group + decide.
    groups: Dict[Tuple[str, Optional[str]], List[Candidate]] = defaultdict(list)
    for c in candidates:
        groups[(c.base, c.tags.disc)].append(c)
    for g in groups.values():
        decide_group(g)

    # Stats.
    keep = sum(1 for c in candidates if c.decision == "keep")
    trim = sum(1 for c in candidates if c.decision == "trim")
    by_reason: Dict[str, int] = defaultdict(int)
    unk_total = 0
    for c in candidates:
        by_reason[c.reason] += 1
        unk_total += len(c.tags.unknown)
    print(f"=== {short}: total={len(candidates)}, keep={keep}, trim={trim} ===")
    for r, n in sorted(by_reason.items(), key=lambda x: -x[1])[:10]:
        print(f"  {n:>6}  {r}")
    print(f"  unknown tag entries: {unk_total}")

    # Write decision CSV.
    decision_path = _phase4_decision_path(short)
    with decision_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["decision", "reason", "path", "base", "regions", "revision",
                    "disc", "flags", "languages", "context", "unknown_tags"])
        for c in sorted(candidates, key=lambda c: (c.decision, c.base, c.path)):
            w.writerow([
                c.decision, c.reason, c.path, c.base,
                ",".join(sorted(c.tags.regions)),
                c.tags.revision_str or "",
                c.tags.disc or "",
                ",".join(sorted(c.tags.disqualify | c.tags.special)),
                ",".join(c.tags.languages),
                ",".join(sorted(c.tags.context)),
                ",".join(c.tags.unknown),
            ])
    print(f"decision CSV: {decision_path}")
    return 0


def cmd_phase4_apply(args) -> int:
    """Hard-link kept files from Archive/Myrient/ into RomM/library/roms/<dest>/.

    Same fs ⇒ hard link is an inode-share; both paths reference the same data.
    `rm` on either side just decrements ref count; file persists until both
    paths are removed. So if we later prune Archive/Myrient/, the curated
    set in RomM stays intact automatically.
    """
    short = args.platform
    if short not in PHASE4_UNITS:
        print(f"unknown phase 4 unit: {short}", file=sys.stderr)
        return 2
    unit = PHASE4_UNITS[short]
    decision_path = _phase4_decision_path(short)
    if not decision_path.exists():
        print(f"ERROR: no decision CSV at {decision_path}; run scan first",
              file=sys.stderr)
        return 2

    links: List[Tuple[str, str]] = []
    with decision_path.open() as f:
        for row in csv.DictReader(f):
            if row["decision"] != "keep":
                continue
            src = _translate_to_gaming(row["path"])
            basename = Path(src).name
            dst = f"{GAMING_DATA_PREFIX}/RomM/library/roms/{unit.dest}/{basename}"
            links.append((src, dst))

    print(f"=== apply {short}: {len(links)} hard-links would be created ===")
    if not args.execute:
        for s, d in links[:10]:
            print(f"  LN {s} -> {d}")
        if len(links) > 10:
            print(f"  ... and {len(links) - 10} more (rerun with --execute)")
        return 0

    lines = ["#!/bin/sh"]
    lines.append(f"mkdir -p '{GAMING_DATA_PREFIX}/RomM/library/roms/{unit.dest}'")
    lines.append("created=0; skipped=0; failed=0")
    for s, d in links:
        sq = s.replace("'", "'\\''")
        dq = d.replace("'", "'\\''")
        lines.append(
            f"if [ -e '{dq}' ]; then skipped=$((skipped+1)); "
            f"elif ln '{sq}' '{dq}' 2>/dev/null; then created=$((created+1)); "
            f"else failed=$((failed+1)); fi"
        )
    lines.append(
        f"echo \"DONE: {short} created=$created skipped=$skipped failed=$failed "
        f"(total: {len(links)})\""
    )
    script = "\n".join(lines) + "\n"
    apply_script = APPLIES_DIR / f"phase4-{short}.sh"
    apply_script.write_text(script)

    print(f"piping {len(links)} ln ops to {GAMING_SSH} ...")
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", GAMING_SSH, "bash"],
        input=script, text=True, capture_output=True,
    )
    print(result.stdout, end="")
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


def cmd_phase4_list(args) -> int:
    """Show phase 4 units and their state."""
    print(f"{'unit':<18} {'sources':<8} {'scanned':<8} {'kept':<8} {'applied':<8}")
    for short, unit in PHASE4_UNITS.items():
        decision_path = _phase4_decision_path(short)
        scanned = decision_path.exists()
        kept = "—"
        if scanned:
            with decision_path.open() as f:
                kept = str(sum(1 for r in csv.DictReader(f) if r["decision"] == "keep"))
        # Could check applied state by counting links, skip for now.
        print(f"{short:<18} {len(unit.sources):<8} {'yes' if scanned else 'no':<8} "
              f"{kept:<8}")
    return 0


# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="create docker volumes + work dir").set_defaults(func=cmd_setup)
    sub.add_parser("teardown", help="remove docker volumes").set_defaults(func=cmd_teardown)

    p_dats = sub.add_parser("dats", help="dat file management")
    dats_sub = p_dats.add_subparsers(dest="dats_cmd", required=True)
    dats_sub.add_parser("list", help="show present vs missing").set_defaults(func=cmd_dats_list)
    dats_sub.add_parser("fetch", help="auto-pull missing dats").set_defaults(func=cmd_dats_fetch)

    p_scan = sub.add_parser("scan", help="igir + rule -> decision CSV (no moves)")
    p_scan.add_argument("platform")
    p_scan.add_argument("--reuse-scan", action="store_true",
                        help="reuse the latest igir CSV; only re-apply the rule")
    p_scan.set_defaults(func=cmd_scan)

    p_apply = sub.add_parser("apply", help="consume decision CSV and mv")
    p_apply.add_argument("platform")
    p_apply.add_argument("--execute", action="store_true",
                         help="actually perform moves; without this, dry-run only")
    p_apply.add_argument("--emit-script", action="store_true",
                         help="with --execute, print the shell script to stdout "
                         "instead of piping to ssh gaming")
    p_apply.set_defaults(func=cmd_apply)

    p_nuke = sub.add_parser("nuke-gba", help="clear GBA scene-pack to Archive/Curated-Trimmed/GBA-scene/")
    p_nuke.add_argument("--execute", action="store_true")
    p_nuke.set_defaults(func=cmd_nuke_gba)

    p4_list = sub.add_parser("phase4-list", help="list phase 4 units and their scan/apply state")
    p4_list.set_defaults(func=cmd_phase4_list)

    p4_scan = sub.add_parser("phase4-scan",
        help="scan an Archive/Myrient/ source set for a new platform; emit decision CSV")
    p4_scan.add_argument("platform", help="phase 4 unit short name (e.g. GBA, NGP, 3DS-Encrypted, PSV-Updates)")
    p4_scan.set_defaults(func=cmd_phase4_scan)

    p4_apply = sub.add_parser("phase4-apply",
        help="hard-link kept files from Archive/Myrient/ into RomM/library/roms/<dest>/")
    p4_apply.add_argument("platform")
    p4_apply.add_argument("--execute", action="store_true",
                          help="actually create the hard links; without this, dry-run only")
    p4_apply.set_defaults(func=cmd_phase4_apply)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
