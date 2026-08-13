# Backlog

Status as of 2026-08-13, after 3.7.0. Each item records the evidence that
raised it, how to verify it, and what can go wrong.

Ordered by return on effort: risks that can be removed with little work come
first.

---

## 1. iPoker: duplicate hands in already-imported databases

**Problem.** The iPoker hand-id fix (2026-07-25) moved `re_hand_info` from
`sessioncode="…"` to `gamecode="…"` — the first pattern also matched the
`<session sessioncode="…">` header that opens every file, assigning the session
id to the first hand in each file. At the time, 9 of 9 files were affected.

**What remains.** The code is fixed, but **the data is not**. In an already
imported database, the first hand in each iPoker file still carries the old id.
Re-importing it inserts the hand under the correct id without replacing the old
row: one duplicate hand per imported file.

**Do not confuse this with the tool shipped in 3.4.2.**
`fpdb_3_legacy/fix_ipoker_duplicate_session_hands.py` (#193) operates on
**XML files on disk**: it finds sessions whose `gamecode` values are all
already covered by a previous file and removes them deterministically. This is
useful *before* import and does not touch the database. Migration of rows that
are already inserted still does not exist — the three `backfill_*` scripts
cover boards, showdown and auto notes, not identifiers.

**To do.** Write a maintenance script that, for every imported iPoker file,
finds the hand whose `siteHandNo` equals a `sessioncode` in the corpus, then
deletes or reconciles it. It should be run once, with a `--dry-run` mode.

**Risk.** High: it deletes database rows. Make `--dry-run` the default, show a
count before taking action, and document the backup procedure. Note that the
3.4.2 tool made the opposite choice — `--dry-run` is an optional flag there,
not the default — because it only touches files that the importer can
regenerate. That reasoning no longer applies once the database is written.

---

## 2. Splitting up `Database.py` — stopped midway

**Status as of 2026-08-13.** 2,231 lines (2,413 before 3.4.2), with a 48.6%
coverage floor (`coverage-baseline.json`, unchanged). `database_players` was
extracted in #194, bringing the number of extracted domains to seven:
`database_aof`, `database_auto_notes`, `database_bulk_import`,
`database_caches`, `database_hud_stats`, `database_players`,
`database_schema`, and `database_tournaments`. The host file is still large.

**To do.** Continue by domain, checking after every extraction that the
complexity ratchet in `pyproject.toml` does not grow: an extraction moves debt;
it must not create more of it.

```bash
ruff check --select C901,PLR0912,PLR0915 --isolated <files>
```

**Risk.** Medium. `Database.py` is central to importing and the HUD; every
extraction must leave the full test suite green.

---

## 3. `gui` domain coverage — 37%, the lowest

**Status.** `coverage-baseline.json` still reports 37.0% for `gui`, versus
83.6% for `poker-domain` and 86.6% for `platform-pkg`. The entry points pull it
down: `fpdb.pyw`, `GuiSessionViewer`, `GuiLogView`, `GuiAutoNotesWorkbench`,
and `ModernSeatPreferences`.

**What changed.** #195 added unit tests for GUI formatting and business logic
(`tests/test_gui_formatting_and_business_logic.py`), and #197 added a Qt
regression test for site cards. The floor has not been ratcheted again: the
value above is the threshold, not today's actual coverage. Regenerating it is
part of the work.

**To do.** Target logic that can be tested without a window — selection,
formatting and filtering — by separating it from Qt wiring. The offscreen `qt`
harness already exists and runs in CI. Then:

```bash
python tools/coverage_ratchet.py --update coverage.json
```

**Risk.** Low, but returns diminish quickly: most of the remaining GUI code is
wiring.

---

## 4. `Configuration` reads XML with minidom

**Problem.** `Configuration.py` parses and rewrites configuration with
`minidom`, the slowest XML parser in the standard library. Measured on a
300-KB `HUD_config.xml` on 2026-08-06:

| | |
|---|---|
| `defusedxml.minidom.parse` | 18.6 ms |
| `ElementTree.parse` | 2.7 ms |

A single `Config()` call makes 566,000 function calls, including 244,000 in
`_get_elements_by_tagName_helper` — `getElementsByTagName` recursively walks
the entire subtree on every call.

**Why this is not urgent.** #197 removed most of the cost: the two example
parses performed by `Config()` are cached, and `Config()` now runs once or
twice per session instead of 27 times. The remaining gain is therefore about
16 ms, once per session.

**Why it is still listed.** Twelve files in `fpdb_3_legacy/` (39 in the whole
repository) manipulate the DOM, including the configuration **write path**;
`Configuration.py` alone makes 134 DOM calls. This is a cross-cutting refactor,
not an optimization — it was deliberately left out of #197 for that reason.

**To do.** If undertaken, give it its own PR, with dedicated round-trip
coverage (read → modify → write → read again) before changing the parser. The
real motivation is configuration-code readability and safety, not speed.

**Risk.** High for user-configuration persistence.

---

## 5. Provision macOS signing/notarization secrets

**Status as of 2026-08-13.** The workflow can sign releases with Developer ID,
hardened runtime and the Apple Events entitlement, then notarize and staple the
macOS bundle when the secrets are configured. 3.7.0 retains an explicit ad-hoc
fallback when `MACOS_SIGNING_IDENTITY` is not provisioned; PR builds remain
deliberately ad hoc.

**Measured effect.** Profiling traces from a 3.4.1 session show paths such as
`/private/var/…/AppTranslocation/…`: each first window opening pays Gatekeeper's
validation cost for the resources it loads.

**To provision.** The six secrets described in
`docs/macos-gatekeeper.md`, using the same Developer ID Application certificate
for PyInstaller, PyOxidizer and all subsequent releases.

**Why.** An ad-hoc signature has a designated requirement tied to the build's
CDHash. Even with a stable `CFBundleIdentifier`, TCC therefore cannot reuse
Screen Recording/Accessibility permissions between versions.

---

## 6. Items awaiting live validation

Neither fixable nor verifiable without a real play session:

- **PokerStars cash bug on Windows** — hardened, never confirmed. The other
  three bugs in the same series are validated.
- **iPoker ring summary** (PMU / bwin 6-max).
- **Bottom-center HUD anchoring** on a 2/3-max Twister.

Handle these when an opportunity arises; there is nothing to do until then.

---

## 7. Translations

Thirteen of the 14 shipped locales are untranslated — only French is complete.
The gettext pipeline, language selector and extraction work; only catalogue
content is missing. This is a translation task, not a development task.

Since 3.4.2, note that #198 fixed language resolution itself: a configuration
without `ui_language` falls back to `system`, not English, so old
configurations are no longer pinned to untranslated strings.

---

## Completed in 3.7.0

Verified in the tree:

- **FastHUD** — the fast-fold HUD lifecycle is hardened: one renderer per
  table, duplicate-instance interlocks, orphan-overlay cleanup, deterministic
  seat rotation and lock-owner diagnostics.
- **Cross-platform contracts** — the macOS and Windows paths are covered by
  deterministic replay tests, and the FastHUD coverage gate remains at 100% in
  CI.
- **Version** — the package, Briefcase bundle and `fpdb_3_legacy.__version__`
  are aligned on 3.7.0.

## Completed in 3.4.2

Verified in the tree, not only in commit messages:

- **Purged `known_failures` list** (#190) — `tests/conftest.py` no longer
  contains the block; the suite reports no `XPASS` (7,394 passed versus
  7,328 passed + 9 xpassed before).
- **Removed `uncalledbets`** (#191) — no occurrence remains in application
  code; only a mention survives in a docstring in
  `tests/helpers/mock_hand.py`. The remove branch was chosen over wiring it to
  `handle_leftover`, and `tests/test_uncalled_bets_real_hands.py` now covers
  accounting on real hands.
- **Performance tests have an execution point** (#192) —
  `.github/workflows/ci.yml:368` runs `python -m pytest -m perf`, on Linux only
  and with `continue-on-error`. Wall-clock budgets are too sensitive to shared
  runner load to block a merge, but the result appears in the log.
- **PartyPoker attribution** (#196) — hands go to the configured skin rather
  than the last `<hhc>` in the configuration file.
- **Popup performance** (#197) — profiling is opt-in (`FPDB_PROFILE=1`), Site
  Preferences no longer scans the disk per card, and the database connection
  survives configuration reloads.

---

## Verified as completed before 3.4.2

Re-read from git history before the old plans were removed:

- **i18n** — `modern_hud_preferences/` contains 167 `_()` calls, and hard-coded
  French labels in `ring_stats/` are gone.
- **Operations scripts** — raised from 0% to a 44.5% floor
  (`tests/test_maintenance_scripts.py`).
- **iPoker hand id** — fixed in code; only data migration remains (item 1).
- **Version displayed by binaries** — the old `"3.0.0alpha"` fallback in
  `fpdb.pyw` was removed in `a5c3a435`; `_resolve_version()` falls back to
  `fpdb_3_legacy.__version__`.
