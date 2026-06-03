#!/usr/bin/env python3
"""
One-shot migration of /srv/.unifi-drive/Gaming/.data/ on `gaming`.

Runs on gaming itself (Python 3.9). Sync from the homelab repo:

    scp ~/Developer/Personal/homelab/bin/migrate-romm-archive.py \
        gaming:~/migrate.py
    ssh gaming "python3 ~/migrate.py <phase> --dry-run"
    ssh gaming "python3 ~/migrate.py <phase>"

Phases (run in order):
    skeleton          create the new directory tree
    myrient-tidy      relocate loose Myrient dirs into Archive/Myrient/
    curate-existing   apply curation rule to platforms already in RomM
    add-new-platforms hard-link curated subsets from Myrient into new RomM platform dirs
    promote-personal  move personal per-platform dirs into RomM (with SHA-1 dedupe)
    extract-vita      unrar the Persona 4 Golden UNDUB-nks multi-part set
    standalone        move PSO2/Minecraft/PC out to Standalone/
    workflow          move RetroArch/dats/saves out to Workflow/
    bios-report       enumerate BIOS coverage gaps

Defaults to --dry-run. Pass --execute to actually move things.
Nothing is ever deleted; "trim" means mv into Archive/Curated-Trimmed/.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT = Path("/srv/.unifi-drive/Gaming/.data")
ARCHIVE = ROOT / "Archive"
ROMM_LIB = ROOT / "RomM" / "library"
ROMM_ROMS = ROMM_LIB / "roms"
ROMM_BIOS = ROMM_LIB / "bios"
STANDALONE = ROOT / "Standalone"
WORKFLOW = ROOT / "Workflow"
MIGRATION_DIR = ROOT / "_migration"
LOG_DIR = MIGRATION_DIR / "logs"

# Existing RomM platform dirs (do not create again, do not touch in skeleton phase)
EXISTING_ROMM_PLATFORMS = [
    "DC", "GB", "GBA", "GBC", "GCN", "NDS", "PS2", "PSP", "PSX", "SNES",
]

# New RomM platform dirs to create
NEW_ROMM_PLATFORMS = [
    "3DS", "PSV", "PSV-Updates",
    "GEN", "SMS", "GG", "N64",
    "SAT", "SCD", "NGCD",
    "NGP", "NGPC", "WS", "WSC", "VB", "PD", "GDC", "PIP",
    "WII", "WIIU", "XBOX",
    "NSW",  # placeholder - just Pokemon Legends Arceus today
]

# 3DS gets multiple subdirs (encrypted/decrypted/digital/cia/undub)
ROMM_3DS_SUBDIRS = ["Encrypted", "Decrypted", "Digital", "CIAs", "UNDUBs"]

# Loose Myrient dirs (top-level under Myrient/) that get moved to Archive/Myrient/Loose/
MYRIENT_LOOSE_DIRS = [
    "Genesis", "N64", "MasterSystem", "GameGear",
    "PSVita-Content", "PSVita-Updates", "Miscellaneous",
]

# Myrient subtrees that move whole into Archive/Myrient/ (preserving their internal structure)
MYRIENT_KNOWN_SUBTREES = ["No-Intro", "Redump", "logs"]


# ---------------------------------------------------------------------------
# Migrator: tracks dry-run / execute and logs every operation


@dataclass
class Migrator:
    dry_run: bool
    log_path: Path
    stats: Dict[str, int] = field(default_factory=lambda: {
        "mkdir": 0, "mv": 0, "link": 0, "skip": 0, "warn": 0,
    })
    _log: Optional[object] = None

    def __post_init__(self):
        if not self.dry_run:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log = self.log_path.open("a")
            self._write(f"\n=== {dt.datetime.now().isoformat()} mode=execute ===")
        else:
            self._write(f"=== {dt.datetime.now().isoformat()} mode=dry-run ===")

    def _write(self, msg: str):
        print(msg)
        if self._log:
            self._log.write(msg + "\n")
            self._log.flush()

    def warn(self, msg: str):
        self._write(f"WARN  {msg}")
        self.stats["warn"] += 1

    def mkdir(self, path: Path):
        if path.exists():
            return
        self._write(f"MKDIR {path}")
        if not self.dry_run:
            path.mkdir(parents=True, exist_ok=True)
        self.stats["mkdir"] += 1

    def move(self, src: Path, dst: Path, *, label: str = "MV") -> bool:
        """Move src -> dst. Refuses to overwrite. Returns True if moved (or would)."""
        if not src.exists() and not src.is_symlink():
            self._write(f"SKIP  {label} (no src) {src}")
            self.stats["skip"] += 1
            return False
        if dst.exists():
            self._write(f"SKIP  {label} (dst exists) {dst}")
            self.stats["skip"] += 1
            return False
        self._write(f"{label:<5} {src}  ->  {dst}")
        if not self.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            # shutil.move handles cross-device; on the same fs, becomes a rename.
            shutil.move(str(src), str(dst))
        self.stats["mv"] += 1
        return True

    def hardlink(self, src: Path, dst: Path) -> bool:
        if not src.exists():
            self._write(f"SKIP  LN (no src) {src}")
            self.stats["skip"] += 1
            return False
        if dst.exists():
            self.stats["skip"] += 1
            return False
        self._write(f"LN    {src}  ->  {dst}")
        if not self.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.link(src, dst)
        self.stats["link"] += 1
        return True

    def summary(self):
        self._write(f"--- summary: {self.stats} ---")
        if self._log:
            self._log.close()


# ---------------------------------------------------------------------------
# Phases


def phase_skeleton(m: Migrator):
    """Create new directory tree. Idempotent. Does not touch existing RomM platform dirs."""
    m._write(">>> phase: skeleton")

    # Top-level
    for d in [ARCHIVE, STANDALONE, WORKFLOW, MIGRATION_DIR, LOG_DIR]:
        m.mkdir(d)

    # Archive subtrees (Myrient/{No-Intro,Redump,logs} are NOT created -
    # the myrient-tidy phase moves them in, and mv refuses if dst exists)
    for d in [
        ARCHIVE / "Myrient" / "Loose",
        ARCHIVE / "Personal",
        ARCHIVE / "Curated-Trimmed",
        ARCHIVE / "Wii-NonRVZ-Originals",
        ARCHIVE / "WiiU-NonWUX-Originals",
    ]:
        m.mkdir(d)

    # New RomM platform dirs
    for p in NEW_ROMM_PLATFORMS:
        m.mkdir(ROMM_ROMS / p)

    # 3DS subdirs
    for sub in ROMM_3DS_SUBDIRS:
        m.mkdir(ROMM_ROMS / "3DS" / sub)


JUNK_NAMES = {"@eaDir", ".DS_Store"}


def phase_myrient_tidy(m: Migrator):
    """
    Empty out the top-level Myrient/ directory by routing each child to its
    destination under Archive/Myrient/. Known subtrees (No-Intro, Redump, logs)
    move directly under Archive/Myrient/; the loose-dir set goes to
    Archive/Myrient/Loose/<name>/; orphan files (downloads, BIOS zips, etc.)
    also go to Archive/Myrient/Loose/<name>.
    """
    m._write(">>> phase: myrient-tidy")
    src_root = ROOT / "Myrient"
    if not src_root.exists():
        m.warn(f"{src_root} does not exist; nothing to do")
        return

    junk_left = 0
    for item in sorted(src_root.iterdir(), key=lambda p: p.name):
        name = item.name
        if name in JUNK_NAMES:
            junk_left += 1
            continue
        if name in MYRIENT_KNOWN_SUBTREES:
            dst = ARCHIVE / "Myrient" / name
        elif name in MYRIENT_LOOSE_DIRS:
            dst = ARCHIVE / "Myrient" / "Loose" / name
        else:
            # Orphan: .partial downloads, [BIOS] zips, loose game files.
            # Park in Loose/ and surface a NOTE so they're easy to find.
            dst = ARCHIVE / "Myrient" / "Loose" / name
            kind = "file" if item.is_file() else "dir"
            m._write(f"NOTE  orphan {kind}: {name}")
        m.move(item, dst)

    if junk_left:
        m._write(
            f"NOTE  {junk_left} NAS-metadata item(s) left in {src_root} "
            f"({sorted(JUNK_NAMES)}); leaving alone"
        )


def phase_not_implemented(name: str) -> Callable[[Migrator], None]:
    def _fn(m: Migrator):
        m._write(f">>> phase: {name}  (not yet implemented)")
        m.warn(f"phase {name!r} is a stub - exit without touching anything")
    return _fn


PHASES: Dict[str, Callable[[Migrator], None]] = {
    "skeleton": phase_skeleton,
    "myrient-tidy": phase_myrient_tidy,
    "curate-existing": phase_not_implemented("curate-existing"),
    "add-new-platforms": phase_not_implemented("add-new-platforms"),
    "promote-personal": phase_not_implemented("promote-personal"),
    "extract-vita": phase_not_implemented("extract-vita"),
    "standalone": phase_not_implemented("standalone"),
    "workflow": phase_not_implemented("workflow"),
    "bios-report": phase_not_implemented("bios-report"),
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("phase", choices=list(PHASES))
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform moves. Without this flag, dry-run only.",
    )
    args = parser.parse_args(argv)

    if not ROOT.exists():
        print(f"ERROR: {ROOT} not found - is this running on `gaming`?", file=sys.stderr)
        return 2

    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = "execute" if args.execute else "dryrun"
    log_path = LOG_DIR / f"{args.phase}-{timestamp}-{suffix}.log"
    m = Migrator(dry_run=not args.execute, log_path=log_path)
    try:
        PHASES[args.phase](m)
    finally:
        m.summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
