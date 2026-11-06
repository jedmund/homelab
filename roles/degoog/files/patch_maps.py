#!/usr/bin/env python3
"""Patch the installed Maps frontend without replacing unrelated upstream code."""
import argparse
from pathlib import Path


REPLACEMENTS = (
    ('return type === "tab:maps" || tab === "maps";',
     'return type === "tab:" + __PLUGIN_ID__ + "-tab" || tab === __PLUGIN_ID__ + "-tab";'),
    ('`/api/plugin/maps/search?q=${encodeURIComponent(query)}&limit=15`',
     '`/api/plugin/${__PLUGIN_ID__}/search?q=${encodeURIComponent(query)}&limit=15`'),
    ('L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {',
     'L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {\n'
     '      referrerPolicy: "strict-origin",'),
)

PLACES_REPLACEMENTS = (
    ("'<img class=\"places-tile\" alt=\"\" draggable=\"false\" src=\"' +",
     "'<img class=\"places-tile\" alt=\"\" draggable=\"false\" referrerpolicy=\"' + "
     "(/^https:\\/\\/(?:[abcd]\\.)?basemaps\\.cartocdn\\.com\\//i.test(src) "
     "? 'strict-origin' : 'no-referrer') + '\" src=\"' +"),
)


def patched(source, replacements=REPLACEMENTS):
    for old, new in replacements:
        if source.count(new) == 1 and old not in source:
            continue
        if source.count(old) != 1 or new in source:
            raise ValueError('Unrecognized Maps frontend; review upstream changes before patching')
        source = source.replace(old, new)
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--places', action='store_true')
    args = parser.parse_args()
    source = args.path.read_text()
    updated = patched(source, PLACES_REPLACEMENTS if args.places else REPLACEMENTS)
    if source == updated:
        print('unchanged')
    else:
        if not args.check:
            args.path.write_text(updated)
        print('changed')


if __name__ == '__main__':
    main()
