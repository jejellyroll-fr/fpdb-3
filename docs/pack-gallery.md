# Pack gallery

fpdb's shareable content is data: `.fpdbhud` HUD packages and `.fpdbstats` stat
packs ([stat-packs.md](stat-packs.md)). The pack gallery is how players share
them: a public repository holds the packages and an `index.json` listing them,
and fpdb installs from it (#449).

This page describes the index format and what fpdb checks before a package can
install. The code is `fpdb_3_legacy/pack_gallery.py`. The in-app browser
(*Tools ▸ Get packs*) and the public repository come next.

## The index

```json
{
  "schema": "fpdb-3/pack-index",
  "version": 1,
  "packs": [
    {
      "id": "fpdb-3.nlhe_6max_basic",
      "kind": "hud",
      "name": "FPDB Basic",
      "version": "1.0.0",
      "min_fpdb_version": "3.9",
      "author": "fpdb-3",
      "license": "AGPL-3.0-or-later",
      "description": "The starter HUD for No Limit Hold'em 6-max.",
      "file": "hud/nlhe_6max_basic.fpdbhud",
      "sha256": "…",
      "size": 5212,
      "screenshot": "screens/nlhe_6max_basic.png",
      "stats": ["vpip", "pfr"]
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `id` | A dotted lower-case namespace, `author.topic`, as for stat packs. The namespaces `fpdb`, `builtin` and `core` are reserved; the project's own packages use `fpdb-3.`. |
| `kind` | `hud` (a `.fpdbhud` package) or `stats` (a `.fpdbstats` stat pack). |
| `name`, `author`, `license`, `description` | What the gallery shows. `license` is required. |
| `version` | The package's version, `1.2` or `1.2.3`. A stat pack's `pack_version` must match it. |
| `min_fpdb_version` | Optional: the oldest fpdb that can use it. |
| `file` | Where the package is, relative to the index; it ends in the kind's suffix. |
| `sha256`, `size` | The package's checksum and size in bytes. |
| `screenshot` | Optional: a picture for the gallery, relative to the index. |
| `stats` | Optional: the stats it shows, for the gallery's preview. |

Any other field is refused, so a typo is not silently ignored.

## What fpdb checks

An index entry that is malformed is set aside with its reason. So is one that
names a kind this fpdb does not know, or is listed twice. The rest of the
index stays usable. An index whose `schema` or `version` this fpdb cannot read
is refused whole.

Before a package installs:

1. **The bytes are the ones the index promised.** The size and SHA-256 must
   match.
2. **The package passes the checks a manual import uses.**
   - A stat pack is read by `stat_packs.read_pack`: it can only name metrics,
     filters and fragments the stat engine registers. There is no SQL and no
     code. Its id and `pack_version` must be the index's.
   - A HUD package is checked by `hud_package.package_problems`:
     - every profile has a name, and its `rows` and `cols`, even when it is
       made of blocks;
     - every grid is at most 100 rows by 100 columns, and every number the
       configuration loader reads (sizes, spans, a block's `x`, `y`,
       `cell_width` and font scales, a profile's padding) is one;
     - every stat, header (`<text>`) and separator (`<hline>`) sits where the
       configuration loader expects it: a valid `_rowcol` (`(row,col)`,
       counted from 1; a header or separator without one sits on `(1,1)`),
       inside the grid, its `colspan` included (`0` makes a separator cross
       the block), and not on a cell another item already takes. Empty cells
       are allowed;
     - every stat it names exists, table stats included, with or without a
       decimal-places suffix (`vpip_0`);
     - every popup it opens is in the package, the shipped library, or the
       stock configuration (`default`, ...).

   A package that fails is refused with the names at fault (for example
   `unknown stat(s): no_such_stat`), and nothing is written.

Packages are data. Nothing in them is imported or run.

The gallery is read over https only, and a redirect to anything else is refused. A package or index larger than its limit
(5 MB per package, 2 MB for the index) is not read whole.

## Offline

The index and every package fetched are kept in a cache. When the gallery
cannot be reached, fpdb lists the cached index, marked as stale, and installs
the packages already cached, after checking them again.

## Updates

A pack is an update when the index has a newer `version` than the one
installed. An installed version that cannot be read counts as older, so a pack
installed by hand can still be updated from the gallery.

## For the packs repository

The repository's CI runs the same checks the app runs:

```bash
python -m fpdb_3_legacy.pack_gallery validate path/to/fpdb-3-packs
```

It lists every problem in the index, every package that is missing, does not
match its checksum or fails its checks, and every missing screenshot. It exits
with 1 if there are any. `pack_gallery.index_entry(path, pack_id=…, kind=…,
name=…, version=…, author=…, license=…)` writes an entry with its size and
checksum filled in.
