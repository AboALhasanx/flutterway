// Package pkg contains the core subsystems and modules of FlutterWay:
//
//   - manifest: Dynamic schema parser and toolchain matrix synchronization.
//   - inspector: Pre-flight checks, Arabic/special path detection, ADB/USB port conflict monitor, WMI virtualization.
//   - downloader: Multi-threaded chunked downloader with resume capabilities and mirror failover.
//   - installer: Subsystem installers for Flutter SDK, Headless Android SDK, OpenJDK 17, and Portable Mode.
//   - doctor: Offline rule engine covering 32 real-world failure patterns with humanized Arabic explanations.
//   - sysenv: Persistent Windows Environment Variables and Registry tweaks (LongPathsEnabled).
//   - gradle: Global gradle.properties optimization, memory tuning, and Windows Root CA SSL truststore injector.
package pkg
