# Codex transition snapshots

These fixtures contain the extracted U-03 through U-05 packages from before the
Codex-native structured-content migration. Tests restore the exact bytes in an isolated
repository and check each complete package against the checksums in
`tests/codex_transition_fixtures.py`.

Source-page PNG files use Base64 encoding so they can be reviewed and transferred as text.
The test helper checks the encoding and restores the original PNG bytes. Do not regenerate
these snapshots during a test run: PDFium raster output can differ across operating systems.
An intentional snapshot update must also update the package checksums and pass regression
tests on macOS and Linux.
