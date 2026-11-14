---
name: flutterway-project-builder
description: Create or extend a student Flutter app using FlutterWay's project structure and offline starter kit. Use when asked to create a Flutter project, feature, screen, or coursework app based on FlutterWay.
---

# FlutterWay Project Builder

## Before editing

1. Read `docs/AGENT_PROJECT_BLUEPRINT.md` and inspect the target project's existing files.
2. Confirm the exact destination. If it already contains a project, preserve it and work only after explicit permission.
3. Do not launch or modify the FlutterWay Desktop application; this workflow builds a separate Flutter project.
4. Check whether Flutter is available on `PATH`; in an extracted offline kit, dot-source `Use-AgentKit.ps1` first. Do not install extra SDKs or access the network unless the user asks.
5. If there is no target project yet, use `agent-kit/offline/create_project.ps1` on Windows with the kit's Flutter SDK available.

## Implementation rules

- Follow the target project's existing conventions; do not force a migration to this blueprint.
- Keep features isolated under `lib/features/<feature>/` and shared app setup under `lib/app/` and `lib/core/`.
- Start with Flutter SDK libraries only. Ask before adding packages or network-fetched assets.
- Keep UI responsive, accessible, and localized according to the user's requested language/direction.
- Add or update widget/unit tests for meaningful behavior.
- Preserve user code, project identity, signing files, and local configuration.

## Verification

Run only commands supported by the local toolchain. The shareable kit includes Flutter/Dart and Temurin JDK, but not Google's Android SDK:

```powershell
flutter pub get --offline
flutter analyze
flutter test
```

Build an APK only when requested and the recipient has installed Android SDK/build dependencies from Google's official source and accepted the applicable licenses:

```powershell
flutter build apk --debug
```

Report every skipped check and its reason. Never claim a build or device run succeeded unless it actually completed and the resulting artifact/device state was checked.
