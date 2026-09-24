#!/usr/bin/env python3
"""Fail closed before Compose can create an empty server directory."""
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
for name, version in (("sky", "21.1.215"), ("atm10", "21.1.215"), ("vanilla", "21.1.217")):
    data = root / name / "data"
    for path in ("world/level.dat", "run.sh", "server.properties", "ops.json"):
        assert (data / path).is_file(), f"{name}: missing {path}"
    assert any((data / "mods").glob("*.jar")), f"{name}: missing mods"
    assert (data / "libraries/net/neoforged/neoforge" / version / "unix_args.txt").is_file()
    manifest = json.loads((data / ".neoforge-manifest.json").read_text())
    assert manifest["minecraftVersion"] == "1.21.1" and manifest["forgeVersion"] == version
    if name in ('sky', 'atm10'):
        pack = json.loads((data / '.curseforge-manifest.json').read_text())
        expected_pack = '1.8' if name == 'sky' else '5.4'
        assert pack['modpackVersion'] == expected_pack, f"{name}: unexpected modpack version"
    properties = dict(line.split("=", 1) for line in (data / "server.properties").read_text().splitlines()
                      if "=" in line and not line.startswith("#"))
    for key, value in {"online-mode": "true", "enable-rcon": "true", "server-port": "25565", "level-name": "world"}.items():
        assert properties.get(key) == value, f"{name}: unexpected {key}"
    assert "\\" not in properties.get("rcon.password", ""), f"{name}: escaped RCON password requires explicit decoding"
    assert properties.get("rcon.password"), f"{name}: missing existing RCON credential"
print("Existing worlds, pinned installations and authentication verified")
