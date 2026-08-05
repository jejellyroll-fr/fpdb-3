# Running the prebuilt macOS builds

The CI artifacts are **not** signed with a Developer ID and are **not** notarized.
macOS therefore attaches the `com.apple.quarantine` attribute to everything that
comes out of a browser download, and Gatekeeper refuses to load the unsigned Qt
libraries the builds ship:

```
Library not loaded: @rpath/libshiboken6.abi3.6.11.dylib
  Reason: ... code signature ... not valid for use in process:
  library load disallowed by system policy
```

Quarantine also makes macOS run `.app` bundles from a read-only App Translocation
mount (`/private/var/folders/…/AppTranslocation/…`), which breaks anything that
writes next to the executable.

## Fix: clear the quarantine attribute

Both artifacts (`fpdb-pyoxidizer-macos-arm64` and `fpdb-build-macos-latest`) ship
an ad-hoc signed `fpdb.app`. Gatekeeper assesses a bundle as a unit, so the app
is approved once instead of once per bundled library:

```bash
mv ~/Downloads/fpdb.app /Applications/
xattr -dr com.apple.quarantine /Applications/fpdb.app
```

Moving the bundle out of `~/Downloads` and clearing the attribute both stop App
Translocation, so the app runs from its real path again.

## Avoiding the problem: extract from the terminal

GitHub Actions serves artifacts as a `.zip` containing a `.tar.gz`. Extracting
that inner archive with Finder/Archive Utility copies the quarantine flag onto
every extracted file; extracting it with the `tar` CLI does not:

```bash
cd ~/Downloads
unzip fpdb-pyoxidizer-macos-arm64.zip
tar -xzf fpdb-pyoxidizer-macos-arm64.tar.gz -C fpdb-pyoxidizer-macos-arm64
```

## Permanent fix

Signing with a Developer ID certificate and notarizing the artifacts
(`codesign --options runtime` + `xcrun notarytool submit`) removes the need for
any of the above. That requires an Apple Developer account and CI secrets, which
this repository does not currently have.
