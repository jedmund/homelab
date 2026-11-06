# Stamp Reactions

Lets logged-in members react to a post with one image stamp. One reaction per
member per post: choosing the stamp you already have removes it, choosing a
different one replaces it. Guests see the counts but not the picker. Post
authors get a notification.

Derived from [SP Post Reactions](https://github.com/soerpaule/sp-post-reactions)
at commit `27db260` (GPL-2.0, (c) 2026 soerpaule). The icon-set, UCP and ACP
machinery was removed in favor of a single stamp set, and the eight fixed
reaction names were replaced by a manifest. The unmodified upstream import is
the first commit of this extension's history.

## Stamps

`stamps.json` is the list, in display order:

```json
{ "key": "awesome", "label": "Awesome!", "file": "awesome.png" }
```

- `key` is stored in the database (lowercase letters, digits, hyphen; at most
  20 characters). Renaming a key orphans existing reactions with the old key.
- `label` is the tooltip, accessible name, and notification text.
- `file` is a PNG in `stamps/`.

Removing a stamp from the manifest hides its existing reactions; the rows stay
in `phpbb_stamp_reactions`. The picker is a six-column grid, so any count that
fits on the page works.

The bundled images are Granblue Fantasy chat stamps copied from the hensei
project. They are game assets, in the same category as the style's sprites.

## Install

The phpbb role bakes this directory into the image, syncs it into
`ext/fireplace/stampreactions` on every start, and enables it. See the role
README.
