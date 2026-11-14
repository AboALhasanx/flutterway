# Changelog

## 1.3.2 — 2026-11-14

- Make large SDK downloads resumable when the server supports HTTP Range, and
  verify completed archives before promoting them for installation.
- Add safe-stop checkpoints to onboarding so setup can resume after interruption.
- Improve Android SDK command-line tooling selection and setup behavior.
- Add the offline FlutterWay Agent Kit, including its project template and
  recipient-side Android SDK/offline-build guides.
- Expand reliability, download, Android SDK adapter, setup checkpoint, and
  JavaScript bridge test coverage.

### Verification

- Windows unit suite: 114 tests passed.
- Reliability fault suite: 81 checks passed.
- PyInstaller package built and its GUI startup smoke test passed.
- Inno Setup 6.7.3 installer compiled; temporary install, launch, and uninstall
  smoke tests passed.

These checks were run locally on Windows. GitHub Actions still runs on push to
`main`; this entry does not imply that a GitHub Release was published.
