# Running the prebuilt macOS builds

Published GitHub Release builds are required by CI to be signed with one stable
Developer ID Application identity, hardened, notarized, and stapled. The
release job fails instead of uploading a macOS archive if the signature is ad
hoc, has no Team ID, uses a designated requirement based on a `cdhash`, lacks
the Apple Events entitlement, or cannot be notarized.

Move `fpdb.app` to `/Applications` before the first launch. macOS can then keep
the app at a stable location and attribute Screen Recording, Accessibility, and
Automation consent to its stable code-signing identity.

## Pull-request and ordinary CI artifacts

Non-release Actions artifacts remain ad-hoc signed because untrusted workflows
do not receive the Apple certificate secrets. They are suitable for testing one
exact build, but their code hash changes on every rebuild; macOS privacy grants
therefore do **not** persist between those artifacts.

A browser also attaches the `com.apple.quarantine` attribute to a downloaded
non-notarized artifact, and Gatekeeper can refuse to load its Qt libraries:

```
Library not loaded: @rpath/libshiboken6.abi3.6.11.dylib
  Reason: ... code signature ... not valid for use in process:
  library load disallowed by system policy
```

Quarantine also makes macOS run `.app` bundles from a read-only App Translocation
mount (`/private/var/folders/…/AppTranslocation/…`), which breaks anything that
writes next to the executable.

## Fix: clear the quarantine attribute

For an ad-hoc CI build only, move it and clear quarantine:

```bash
mv ~/Downloads/fpdb.app /Applications/
xattr -dr com.apple.quarantine /Applications/fpdb.app
```

Do not re-sign a published release ad hoc: doing so discards its Developer ID
identity and invalidates the stable privacy grants this packaging is designed to
preserve.

## Avoiding the problem: extract from the terminal

GitHub Actions serves artifacts as a `.zip` containing a `.tar.gz`. Extracting
that inner archive with Finder/Archive Utility copies the quarantine flag onto
every extracted file; extracting it with the `tar` CLI does not:

```bash
cd ~/Downloads
unzip fpdb-pyoxidizer-macos-arm64.zip
tar -xzf fpdb-pyoxidizer-macos-arm64.tar.gz -C fpdb-pyoxidizer-macos-arm64
```

## Release credential setup

The release workflow expects these repository secrets:

- `MACOS_SIGNING_IDENTITY`: the full Developer ID Application identity;
- `MACOS_CERTIFICATE_P12_BASE64` and `MACOS_CERTIFICATE_PASSWORD`;
- `MACOS_NOTARY_API_KEY_P8_BASE64`, `MACOS_NOTARY_KEY_ID`, and
  `MACOS_NOTARY_ISSUER_ID`.

The same certificate must be used for both the PyInstaller and PyOxidizer
variants and for every subsequent release. Replacing it changes the designated
requirement and may require users to grant the privacy permissions again.
