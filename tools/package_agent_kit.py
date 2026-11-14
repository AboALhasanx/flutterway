"""Build the redistributable FlutterWay agent kit for Windows x64."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"
PACKAGE_NAME = f"FlutterWay-Agent-Kit-v{VERSION}-windows-x64-offline"
DEFAULT_OUTPUT = ROOT / "dist" / "agent-kit"
LOCK_PATH = ROOT / "agent-kit" / "offline" / "toolchain.lock.json"

STATIC_FILES: tuple[tuple[Path, str], ...] = (
    (Path("AGENTS.md"), "AGENTS.md"),
    (Path("LICENSE"), "LICENSE"),
    (
        Path(".agents/skills/flutterway-project-builder/SKILL.md"),
        ".agents/skills/flutterway-project-builder/SKILL.md",
    ),
    (Path("docs/AGENT_PROJECT_BLUEPRINT.md"), "docs/AGENT_PROJECT_BLUEPRINT.md"),
    (Path("agent-kit/offline/README.md"), "README.md"),
    (Path("agent-kit/offline/create_project.ps1"), "create_project.ps1"),
    (Path("agent-kit/offline/Use-AgentKit.ps1"), "Use-AgentKit.ps1"),
    (Path("agent-kit/offline/Setup-AndroidSDK.ps1"), "Setup-AndroidSDK.ps1"),
    (Path("agent-kit/offline/Warm-OfflineBuild.ps1"), "Warm-OfflineBuild.ps1"),
    (Path("agent-kit/offline/toolchain.lock.json"), "toolchain.lock.json"),
    (Path("agent-kit/offline/template/README.md"), "template/README.md"),
    (Path("agent-kit/offline/template/pubspec.yaml"), "template/pubspec.yaml"),
    (Path("agent-kit/offline/template/pubspec.lock"), "template/pubspec.lock"),
    (Path("agent-kit/offline/template/analysis_options.yaml"), "template/analysis_options.yaml"),
    (Path("agent-kit/offline/template/lib/main.dart"), "template/lib/main.dart"),
    (Path("agent-kit/offline/template/lib/app/app.dart"), "template/lib/app/app.dart"),
    (Path("agent-kit/offline/template/lib/app/app_theme.dart"), "template/lib/app/app_theme.dart"),
    (
        Path("agent-kit/offline/template/lib/features/home/presentation/home_page.dart"),
        "template/lib/features/home/presentation/home_page.dart",
    ),
    (Path("agent-kit/offline/template/test/widget_test.dart"), "template/test/widget_test.dart"),
)

STORED_SUFFIXES = {
    ".7z", ".a", ".bin", ".dll", ".gz", ".jar", ".jpg", ".jpeg", ".lib",
    ".pak", ".pdb", ".png", ".so", ".snapshot", ".webp", ".zip",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def add_tree(archive: zipfile.ZipFile, source: Path, archive_root: str) -> int:
    count = 0
    for item in sorted(source.rglob("*")):
        if not item.is_file():
            continue
        relative = item.relative_to(source).as_posix()
        arcname = f"{PACKAGE_NAME}/{archive_root}/{relative}"
        compression = zipfile.ZIP_STORED if item.suffix.lower() in STORED_SUFFIXES else zipfile.ZIP_DEFLATED
        archive.write(item, arcname, compress_type=compression, compresslevel=1 if compression == zipfile.ZIP_DEFLATED else None)
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flutter-sdk", type=Path, required=True, help="Verified Flutter SDK directory with Android engine artifacts precached")
    parser.add_argument("--jdk", type=Path, required=True, help="Verified Temurin JDK 21 directory")
    parser.add_argument("--pub-cache", type=Path, required=True, help="Curated pub cache populated from the starter template")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    flutter = args.flutter_sdk.resolve()
    jdk = args.jdk.resolve()
    pub_cache = args.pub_cache.resolve()
    required = [ROOT / source for source, _ in STATIC_FILES]
    missing = [str(path) for path in required if not path.is_file()]
    for label, root, relative in (
        ("Flutter SDK", flutter, Path("bin/flutter.bat")),
        ("Temurin JDK", jdk, Path("bin/java.exe")),
        ("Temurin legal notices", jdk, Path("legal")),
    ):
        if not (root / relative).exists():
            missing.append(f"{label}: {root / relative}")
    if not pub_cache.is_dir():
        missing.append(f"Starter pub cache: {pub_cache}")
    if missing:
        print("Missing package inputs:\n- " + "\n- ".join(missing), file=sys.stderr)
        return 1

    release_file = jdk / "release"
    release_text = release_file.read_text(encoding="utf-8", errors="replace")
    if 'JAVA_VERSION="21.0.13"' not in release_text or 'IMPLEMENTOR="Eclipse Adoptium"' not in release_text:
        print("The supplied JDK is not the pinned Eclipse Temurin 21.0.13 release.", file=sys.stderr)
        return 1

    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    flutter_version = lock["components"]["flutter"]["version"]
    engine_version_file = flutter / "bin" / "internal" / "engine.version"
    if not engine_version_file.is_file():
        print("Flutter engine.version is missing; input does not look like a Flutter SDK.", file=sys.stderr)
        return 1
    expected_flutter_sha = lock["components"]["flutter"]["sha256"]
    expected_jdk_sha = lock["components"]["temurin_jdk"]["sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", expected_flutter_sha) or not re.fullmatch(r"[0-9a-f]{64}", expected_jdk_sha):
        print("Toolchain lock file contains an invalid SHA-256.", file=sys.stderr)
        return 1

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{PACKAGE_NAME}.zip"
    checksum_path = output_dir / f"{PACKAGE_NAME}.zip.sha256"
    if archive_path.exists() or checksum_path.exists():
        print(f"Refusing to overwrite existing output: {archive_path}", file=sys.stderr)
        return 1

    output_root = f"{PACKAGE_NAME}/"
    manifest: dict[str, object] = {
        "name": "FlutterWay Agent Kit",
        "version": VERSION,
        "target": "Windows x64",
        "offline_capabilities": ["Flutter project scaffolding", "Dart analysis", "starter widget tests", "project-specific offline APK builds after recipient-side online setup and cache warm-up"],
        "not_included": ["Google Android SDK/build-tools (recipient-side installer included)", "Android Studio/VS Code binaries", "emulator images", "arbitrary third-party package caches"],
        "flutter": {
            "version": flutter_version,
            "official_archive_sha256": expected_flutter_sha,
            "precache_scope": "Android engine artifacts only",
        },
        "starter_pub_cache": "toolchain/pub-cache/",
        "android_sdk_setup": {
            "distribution": "Download from the official Google repository on the recipient's computer.",
            "license_acceptance": "Interactive; the recipient must review and accept locally.",
            "setup_script": "Setup-AndroidSDK.ps1",
            "offline_cache_warmup_script": "Warm-OfflineBuild.ps1",
        },
        "temurin_jdk": {
            "version": "21.0.13+9",
            "official_archive_sha256": expected_jdk_sha,
            "license_notices_path": "toolchain/jdk/legal/",
        },
    }

    try:
        with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
            for source, destination in STATIC_FILES:
                path = ROOT / source
                archive.write(path, f"{output_root}{destination}", compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
            manifest["file_count"] = (
                len(STATIC_FILES) + 1
                + add_tree(archive, flutter, "toolchain/flutter")
                + add_tree(archive, jdk, "toolchain/jdk")
                + add_tree(archive, pub_cache, "toolchain/pub-cache")
            )
            archive.writestr(f"{output_root}manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise

    digest = sha256_file(archive_path)
    checksum_path.write_text(f"{digest}  {archive_path.name}\n", encoding="ascii")
    print(f"Archive: {archive_path}")
    print(f"SDK source size: {tree_size(flutter) + tree_size(jdk):,} bytes")
    print(f"Compressed size: {archive_path.stat().st_size:,} bytes")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
