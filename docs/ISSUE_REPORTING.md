# Reporting an issue safely

Every bug report and feature request must state the FPDB version it concerns.
Use **Help → About** to copy the version and build information, or provide the
exact release tag or commit. A report without a version cannot establish which
behavior or UI it describes.

## Capture evidence without exposing player data

Prefer a deterministic demo screenshot when the issue is visual:

```bash
uv run python tools/make_demo_db.py
uv run python tools/capture_wiki_screenshots.py
```

The demo database uses invented players and the renderer runs offscreen. If a
real table screenshot is necessary, redact every player name, account id, room
identifier, token, local path, and unrelated application before sharing it.

Use the repository redaction tool rather than blur or ordinary pixelation:

```bash
uv run python tools/anonymize_screenshot.py table.png \
  --output table-anon.png \
  --box 120,340,180,22 \
  --box 410,190,180,22
```

The default `fill` mode permanently paints each selected rectangle and rewrites
the image without EXIF, ICC, or PNG text metadata. `--relative` accepts
coordinates as fractions of the image, and `--mode pixelate` is available only
when preserving the approximate layout matters. The tool does not detect names
automatically: inspect the output at full resolution before uploading it.

## Captures, logs, and hand histories

Raw `.raw`, `.pcap`, hand-history files, and unfiltered logs can contain player
names, table names, account paths, session identifiers, tokens, or plaintext
client messages. Do not attach them directly to a public issue.

Instead:

1. reproduce the problem with a minimal capture;
2. export the smallest normalized or summary view that demonstrates it;
3. remove or replace identifying values consistently;
4. inspect the result as text and as an image before uploading it;
5. state the FPDB version, operating system, room, format, and relevant macOS
   permissions alongside the evidence.

For SwC native capture, the report commands such as `--inspect`,
`--session-summary`, `--normalized-json`, and `--importability-audit` are
capture-only diagnostics. They do not make a raw archive safe to publish. The
archive remains private until its contents and metadata have been reviewed.

For macOS HUD reports, include the state of **Screen Recording**,
**Accessibility**, and **Automation** permissions, and whether the build is a
Developer ID/notarized release or an ad-hoc artifact. See
[`docs/macos-gatekeeper.md`](macos-gatekeeper.md) for the permission model.
