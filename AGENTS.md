# Agent instructions

For tasks that create or extend a student Flutter app using FlutterWay's conventions, read:

1. [`docs/AGENT_PROJECT_BLUEPRINT.md`](docs/AGENT_PROJECT_BLUEPRINT.md) — architecture and quality rules.
2. [FlutterWay Project Builder skill](.agents/skills/flutterway-project-builder/SKILL.md) — task workflow and safety rules.
3. [`agent-kit/offline/README.md`](agent-kit/offline/README.md) — offline local project generator.

**Important:** FlutterWay itself is a Python + pywebview Windows app. Do not launch or modify FlutterWay Desktop when the user asks you to create a separate Flutter project. Work only in the destination the user specifies; never overwrite an existing project. Do not install SDKs, add network dependencies, or run destructive commands without permission.

The shareable offline kit includes the Flutter SDK, Temurin JDK, instructions, and starter template. It does not include Google's Android SDK or VS Code binaries; Android SDK/build tools are required to build an APK, and the recipient must obtain/accept Google's SDK licenses from the official source.
