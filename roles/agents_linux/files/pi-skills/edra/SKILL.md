---
name: edra
description: Reference for the Edra rich text editor (Svelte 5 + Tiptap v3 + Tailwind v4, v2.4.2). Use when working with Edra components (EdraEditor, EdraToolBar, EdraBubbleMenu, DragHandle, EdraDragHandleExtended, ToC), Edra extensions, slash commands, bubble menus, tables, math, file uploads, find-and-replace, drag-and-drop, or troubleshooting/configuring an Edra editor in a Svelte project. Also use for questions about Edra installation (shadcn vs headless flavor) and the component-based API surface.
---

# Edra Documentation

Authoritative reference for [Edra](https://edra.tsuzat.com/) v2.4.2 — a component-based rich text editor for Svelte 5 built on Tiptap v3. The docs are served by the `edra-docs` CLI in this skill so they stay in sync with the upstream source.

## Setup

No setup needed — `edra-docs` ships with the `edra-mcp-server` repo. Verify it's reachable:

```bash
node /Users/justin/Developer/Personal/edra-mcp-server/dist/cli.js list
```

If the path moves, update the references in this file.

## Usage

### List all documentation sections

```bash
node /Users/justin/Developer/Personal/edra-mcp-server/dist/cli.js list
```

The slugs returned by `list` are the source of truth — they're generated directly from Edra's upstream headings (one entry per `#` chapter and per `##` subsection). Don't memorize a specific list; run `list` to discover.

### Read a specific section

```bash
node /Users/justin/Developer/Personal/edra-mcp-server/dist/cli.js show <slug>
```

Pass `all` as the slug to dump every section.

### Search across all sections (recommended starting point)

```bash
node /Users/justin/Developer/Personal/edra-mcp-server/dist/cli.js search "<query>"
```

Multi-word queries are tokenized; sections matching any term are returned, ranked by how many distinct terms they hit (more focused sections preferred on ties). Returns previews — `show <slug>` for the full content.

## When to use which command

- **Specific topic or symbol mentioned (e.g. "drag handle customNodes", "math", "slash commands")**: `search` first, then `show` the most relevant slug.
- **"How do I install Edra"**: `show installation`.
- **General Edra question or you want the whole picture**: `show all` for everything, or `show introduction` for a brief overview.

## Quick facts (no CLI needed)

- Two UI flavors: **shadcn** (polished, opinionated) and **headless** (class-driven, minimal). Both copy source into `src/lib/components/edra/` via `npx edra@next init <flavor>`.
- The library is **component-based**, not function-based. There is no `initiateEditor()` API — use `<EdraEditor bind:editor />` and the Tiptap editor instance.
- Built on Tiptap v3 (`@tiptap/core` ^3.13). Uses StarterKit, plus Edra's custom extensions for media, slash commands, tables, math, and find/replace.
- Heading levels supported: 1–4.
- Default code-block highlighting via lowlight (one-dark theme).
