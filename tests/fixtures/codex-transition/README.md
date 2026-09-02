# Codex transition snapshots

These fixtures preserve the extracted U-03 through U-05 packages that existed before the
Codex-native structured-content migration. Tests restore these bytes into an isolated
repository and verify each complete package against the checksums in
`tests/codex_transition_fixtures.py`.

The source-page PNG files are Base64-encoded so the repository can review and transport the
fixtures as text. The test helper validates the encoding and restores the original PNG bytes.
Do not regenerate these snapshots during a test run because PDFium raster output can differ
across operating systems. Any intentional snapshot update must include the corresponding
package checksum changes and regression-test validation on macOS and Linux.
