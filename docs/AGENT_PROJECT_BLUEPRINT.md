# FlutterWay Agent Project Blueprint

**Language:** [English](AGENT_PROJECT_BLUEPRINT.md) · FlutterWay's desktop UI remains Arabic.

This document describes how a coding agent should create or extend a **separate student Flutter app** using FlutterWay's conventions. It does not describe the architecture of FlutterWay Desktop, which is Python + pywebview.

## 1. Intended workflow

The user supplies a project request and a destination. The agent should:

1. Read this blueprint and the target project's existing files.
2. Confirm the destination and whether it is new or existing.
3. Reuse the offline starter kit for a new project, or preserve and adapt an existing project.
4. Implement the requested scope without launching FlutterWay Desktop.
5. Run local/offline checks supported by the installed Flutter SDK and report exact results.

The agent must not install Flutter/Android SDKs, add network dependencies, overwrite an existing project, alter signing configuration, or make destructive changes without explicit user authorization.

## 2. Default project layout

Use this lightweight feature-first structure when the project does not already have a suitable convention:

```text
lib/
├── main.dart
├── app/
│   ├── app.dart             # MaterialApp, routes, app-level configuration
│   └── app_theme.dart       # Color scheme and typography
├── core/
│   ├── constants/           # App-wide constants only
│   ├── utils/               # Pure reusable helpers
│   └── widgets/             # Truly shared widgets
└── features/
    └── <feature>/
        ├── data/             # Optional: models and data sources when needed
        ├── domain/           # Optional: business rules when needed
        └── presentation/
            ├── pages/
            └── widgets/
test/
└── ..._test.dart
```

Do not create empty layers just to match the diagram. For small coursework apps, keep the feature simple and use Flutter's built-in `setState`; use `ChangeNotifier` or a user-requested state package only when complexity justifies it. Avoid adding architecture or dependencies the task does not need.

## 3. Code and UI conventions

- Keep `main.dart` small; initialize only what the app actually needs and launch the app widget.
- Use `const` constructors where practical, meaningful widget names, and one responsibility per widget.
- Keep business/data access out of large `build()` methods. Extract pure logic so it can be tested.
- Use Material 3 unless the brief specifies another design system.
- Make layouts usable on narrow phones and larger screens; avoid fixed widths that overflow.
- Provide semantic labels, visible focus/tap affordances, sufficient contrast, and scalable text.
- Match the requested language and text direction. Do not assume that every generated app must be Arabic just because FlutterWay's UI is Arabic.
- Keep dependencies in `pubspec.yaml` minimal. Prefer SDK APIs; ask before adding a package that needs network access.
- Never put API keys, signing credentials, personal paths, or private device identifiers into source control.

## 4. Offline and toolchain contract

The shareable offline kit bundles the Flutter/Dart SDK, a Temurin JDK, source templates, a local generator, and scripts to install Android SDK components from Google on the recipient computer and warm project-specific caches. It intentionally does **not** bundle Google's Android SDK, Android Studio/VS Code binaries, Android emulator images, or arbitrary third-party packages.

- Project scaffolding, Dart analysis, and starter widget tests can run offline from the bundled Flutter SDK/JDK.
- Android APK builds still need Android SDK platform/build-tools and Gradle/Maven artifacts. Run `Setup-AndroidSDK.ps1` on the recipient computer while online; review and accept licenses there. Google SDK binaries are not mirrored or redistributed in the shareable kit.
- For later offline APK builds on that same computer, run `Warm-OfflineBuild.ps1 -Project <path>` once while online. It caches dependencies locally for the selected project and verifies an offline build; those caches are not packaged or transferred by the kit.
- `flutter pub get --offline` works only when every requested package is already cached. The kit includes a lockfile and the small pub cache needed for the starter's Flutter test dependencies; it does not cache arbitrary packages added later.
- If a check needs missing tools or uncached artifacts, stop and report that limitation; do not silently enable online downloads.

## 5. Offline starter generator

On Windows, from a repository checkout:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\source" | Out-Null
.\agent-kit\offline\create_project.ps1 `
  -ProjectName campus_tasks `
  -Destination "$env:USERPROFILE\source\campus_tasks" `
  -Organization com.example
```

For a repository checkout, Flutter must already be on `PATH`. In an extracted kit, both scripts are in the kit root rather than `agent-kit\offline`; dot-source `Use-AgentKit.ps1` in the current PowerShell session before running the generator. The generator refuses to overwrite an existing destination, uses `flutter create --no-pub`, copies the FlutterWay starter source, and runs `flutter pub get --offline`. It does not install tools or contact the network.

## 6. Verification ladder

Run these from the generated project's directory when the local SDK supports them:

```powershell
flutter pub get --offline
flutter analyze
flutter test
```

Run `flutter build apk --debug` only when the user requested an APK and the local Android toolchain is ready. For device installation/run, ask which connected device to use; never assume or silently select among multiple devices. Report command, result, and skipped checks honestly.

## 7. Scope boundary

This kit is **agent guidance plus a project scaffold**, not an agent runtime, remote-control service, or replacement for FlutterWay Desktop's setup/diagnostic features. It lets an agent work directly in a Flutter project when that agent already has local filesystem/terminal access and a Flutter SDK. The public repository URL alone does not grant access to a user's machine or files.
