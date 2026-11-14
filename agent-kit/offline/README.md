# FlutterWay Offline Agent Kit

This folder is a locally usable handoff kit for coding agents. The shareable archive also includes a Flutter/Dart SDK with Android engine artifacts and a Temurin JDK, in addition to this blueprint, the `flutterway-project-builder` skill, and a dependency-free starter source template.

## Download the shareable archive

- [FlutterWay Agent Kit v1.0.0 for Windows x64 (MEGA)](https://mega.nz/file/gy1TiJbK#kvhHFPNPDMgD06bZf5ozKk0TJOyIEI5xoPS44fZL4Ck)
- Verify the downloaded ZIP with `Get-FileHash .\FlutterWay-Agent-Kit-v1.0.0-windows-x64-offline.zip -Algorithm SHA256` and compare it with the expected value documented in the repository's offline kit guide.
- Do not commit the multi-gigabyte ZIP to Git. Keep it on MEGA and commit only these instructions and source files.
- Recipient-side setup, project creation, and offline build steps are described below in this README; the repository also has an [Arabic walkthrough](https://github.com/AboALhasanx/flutterway/blob/main/docs/OFFLINE_AGENT_KIT.ar.md).

## What is included

- Agent workflow and safety instructions.
- A minimal Flutter app source tree using only Flutter SDK libraries.
- Flutter SDK and Dart SDK, including Android Flutter engine artifacts for offline source analysis/tests.
- Temurin JDK 21.
- A PowerShell generator that creates Android project scaffolding and resolves starter packages offline.
- A verified Android command-line-tools bootstrapper that downloads Google SDK components directly on the recipient's computer.
- A project-specific warm-up script that downloads Gradle/Maven/pub dependencies once and checks later offline builds.

## What is not included

- Google's Android SDK/platform/build-tools binaries (a recipient-side installer is included), Android Studio/VS Code binaries, emulator images, and OEM USB drivers.
- Arbitrary third-party pub packages and Gradle/Maven dependencies for user-selected plugins. Only the packages needed for the starter app's offline test command are cached.
- An agent executable or remote-control capability.

The kit is sufficient for offline Flutter project scaffolding, Dart analysis, and starter tests. It is **not sufficient for offline APK builds on a blank computer**. Google's SDK components must be downloaded from Google on the recipient computer, and the recipient must review and accept the SDK licenses there. The Android installer does not auto-accept licenses. Google SDK binaries are excluded from the MEGA-shareable archive; see [Google's Android SDK terms](https://developer.android.com/studio/terms).

## Set up Android and prepare local offline builds

This one-time setup requires internet on the recipient computer. In PowerShell at the extracted kit root:

```powershell
. .\Use-AgentKit.ps1
.\Setup-AndroidSDK.ps1
```

Review and accept the interactive Android SDK license prompts yourself. This installs command-line tools, platform-tools (ADB), Android platform 36, and build-tools 36.0.0 from Google's official repository. Restart PowerShell after setup if the persistent environment variables are not visible. Android Studio, emulator system images, and OEM USB drivers are not included; a physical device can be used if its matching driver is installed.

Generate the project, then run its first Android build while online to populate local Gradle/Maven and pub caches:

```powershell
.\create_project.ps1 -ProjectName campus_tasks -Destination "$env:USERPROFILE\source\campus_tasks" -Organization com.example
.\Warm-OfflineBuild.ps1 -Project "$env:USERPROFILE\source\campus_tasks"
```

After that succeeds, the script verifies `flutter pub get --offline`, analysis, tests, and an offline debug APK build on that same computer. User-added plugins or changed dependency versions require another online warm-up. Caches remain in the local user profile; they are not collected into or redistributed with the archive. This supports offline work after preparation; it cannot install restricted Google SDK packages on a completely disconnected new machine.

## Generate a project

After extracting the archive, from PowerShell:

```powershell
# Run these from the extracted kit root.
. .\Use-AgentKit.ps1
New-Item -ItemType Directory -Force "$env:USERPROFILE\source" | Out-Null
.\create_project.ps1 `
  -ProjectName campus_tasks `
  -Destination "$env:USERPROFILE\source\campus_tasks" `
  -Organization com.example
```

The destination must not exist. After generation, the script runs `flutter pub get --offline`. Review the generated project and then run:

```powershell
Set-Location "$env:USERPROFILE\source\campus_tasks"
flutter analyze
flutter test
```

The archive includes the Flutter and Temurin JDK licenses/notices. Android SDK and VS Code must be obtained through their official distribution channels. For full conventions, see `docs/AGENT_PROJECT_BLUEPRINT.md` in the repository or the included copy.
