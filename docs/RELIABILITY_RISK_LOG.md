# FlutterWay reliability and performance log

**Run date:** 2026-11-06 · **Scope:** Windows local checks, offline-kit packaging, Flutter release resolution, and bounded HTTP probes. This is a point-in-time smoke/performance sample, not a fleet benchmark.

## Findings and dispositions

| ID | Severity / state | Finding | Evidence and follow-up |
|---|---|---|---|
| R-001 | High · Mitigated | Interrupted Flutter, JDK, and Android command-line-tools downloads now keep a `.part` checkpoint and request HTTP Range on retry. | `gui/downloads.py::resumable_download` checks the returned `Content-Range` start before appending, restarts cleanly if a server ignores Range, handles a complete partial via HTTP 416, retries transient errors, preserves partial bytes on cooperative cancellation, and leaves SHA-256 verification to the installing caller. Unit tests cover range append, ignored range, interrupted transfer, completed-part recovery, and safe cancellation. Live rate remains dependent on network/CDN. |
| R-002 | Medium · Mitigated with fallback | Android SDK management prefers Google's Android CLI when installed, and retains pinned `sdkmanager` as a compatibility fallback. | Official [Android CLI SDK install reference](https://developer.android.com/tools/agents/android-cli/commands/sdk_install) documents `android --sdk=<path> sdk install platforms/android-36`; Android CLI's release notes state accepted licenses remain compatible with SDK tools and Gradle. Calls opt out of CLI metrics and use the user's existing CLI installation; no unpinned Android CLI binary is silently added. CI still needs an opt-in smoke run against the real Windows CLI distribution. |
| R-003 | High · Expected limitation | “Offline on a new computer from first boot” is not supported by the shareable kit. | Google SDK packages and project-specific Gradle/Maven caches are intentionally not redistributed. Gradle offline mode fails if any required module or repository metadata is absent; caches are repository-specific and version-sensitive. Each target computer needs a one-time online SDK install/license acceptance and a successful project warm-up. See [Gradle dependency caching/offline mode](https://docs.gradle.org/current/userguide/dependency_caching.html) and the [Android SDK license terms](https://developer.android.com/studio/terms). |
| R-004 | Medium · Fixed | Android setup persisted `ANDROID_HOME` but did not persist `platform-tools` on the user's PATH. | A new shell could have the SDK configured while `adb` was not discoverable by name. `Setup-AndroidSDK.ps1` now adds `platform-tools` idempotently to both the current process and user PATH. A mocked sdkmanager smoke test confirmed environment persistence and restored the machine's prior user variables afterward. |
| R-005 | Medium · Open | Real SDK installation/APK/device checks are not part of every local unit-test run. | The default CI runs unit tests and resolves the live Flutter manifest; full Flutter download and Android APK build are opt-in workflow inputs. `python tests/audit_smoke.py` stopped at `paths.flutter_version()` because this host has no configured local Flutter SDK. Keep manual/CI jobs and capture duration, exit code, selected SDK packages, and artifact hash on clean Windows runners. |

## Measurements from this run

| Check | Result |
|---|---:|
| Local Python unit suite | 101 tests passed in 2.470 s (2.913 s process wall time) |
| Local browser failure/state smoke | 77/77 checks passed in 39.114 s |
| Flutter release manifest lookup | Stable `3.47.9`, 0.57 s |
| Flutter Storage HTTP probe | HTTP 206; 8 MiB in 4.81 s (1.66 MiB/s); advertised object size 1,939,451,626 bytes |
| Google Android tools HTTP probe | HTTP 206; 8 MiB in 2.65 s (3.02 MiB/s); advertised object size 153,583,359 bytes |
| Offline kit archive | 7-Zip integrity check passed; 30,858 files; SHA-256 recorded in adjacent `.sha256` sidecar |

HTTP probes requested and read at most 8 MiB from each official Google host. The extrapolated Flutter duration is only a rough sample; CDN routing, congestion, and the recipient's ISP can change it substantially. MEGA itself was not benchmarked, and the supplied MEGA page returned no readable content to the web fetcher.

The host-specific `tests/audit_smoke.py` did not complete: static checks passed, then its path precondition failed because Flutter is not configured on this workstation. This is an environment blocker, not a passing result.

## Remediation validation (2026-11-06)

- Added cooperative **إيقاف التجهيز عند نقطة آمنة** to onboarding. It persists a minimal atomic checkpoint (`stage`, percentage, status, timestamp), cancels active file transfers without promoting incomplete data, and marks non-interruptible SDK operations to stop at their next stage boundary. Retrying re-runs idempotent checks and reuses already-installed files/caches.
- Added an Android SDK-manager adapter that prefers Android CLI if already installed, uses `--no-metrics`, and falls back to the pinned Google command-line tools' `sdkmanager`. The downloaded package manager remains SHA-256 pinned.
- To opt into Google's maintained Android CLI before running FlutterWay, install it from an elevated/non-elevated PowerShell as appropriate with `winget install --id Google.AndroidCLI`; otherwise FlutterWay retains the sdkmanager fallback. Installation is not silently triggered by the app.
- TDD evidence: tests were first run before `resumable_download` existed and failed with `AttributeError`; they pass after implementation. The follow-up suite covers range mismatch/restart, retry-resume, HTTP 416, cancellation preservation, checkpoint persistence, Android CLI args, and stop request UI behavior.
- Latest local verification: `python -m unittest discover -s tests` → 112 passed in 4.048 s; `python tests/reliability_faults.py` → 81/81 passed; `py_compile` and `git diff --check` passed.
- Local HTTP integration probe seeded an 11-byte `.part`, served a standards-compliant `206 Content-Range`, resumed to 41 bytes, and verified the final SHA-256 successfully.
- Remaining operational check: run the opt-in clean-Windows APK build once with Android CLI installed, then once on the sdkmanager-only fallback; no actual SDK or connected-device run was performed on this workstation.

## Sources

- [Android `sdkmanager` reference](https://developer.android.com/tools/sdkmanager)
- [Android SDK License Agreement](https://developer.android.com/studio/terms)
- [Gradle dependency cache and offline mode](https://docs.gradle.org/current/userguide/dependency_caching.html)
- [PowerShell `Invoke-WebRequest`](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/invoke-webrequest?view=powershell-7.6)
- [Android CLI SDK package installation](https://developer.android.com/tools/agents/android-cli/commands/sdk_install)
- [Android CLI release notes](https://developer.android.com/tools/agents/android-cli/release-notes)
