"""Strip debug sections from APK native libraries and re-sign the APK.

The Flutter engine artifacts can be unstripped (hundreds of MB of .debug_*).
Android's AGP only strips with the NDK, which FlutterWay deliberately avoids.
This module does the same job with the small ELF stripper in elf_strip.py and
the Android SDK's zipalign/apksigner.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile

try:
    from gui import elf_strip, paths
except ImportError:
    import elf_strip
    import paths


def _version_key(name: str):
    parts = []
    for part in name.replace("-", ".").split("."):
        parts.append(int(part) if part.isdigit() else -1)
    return tuple(parts)


def _build_tools() -> str | None:
    root = os.path.join(paths.android_sdk_root(), "build-tools")
    if not os.path.isdir(root):
        return None
    for version in sorted(os.listdir(root), key=_version_key, reverse=True):
        folder = os.path.join(root, version)
        if os.path.exists(os.path.join(folder, "zipalign.exe")) and os.path.exists(os.path.join(folder, "apksigner.bat")):
            return folder
    return None


def _debug_keystore() -> str | None:
    candidate = os.path.expandvars(r"%USERPROFILE%\.android\debug.keystore")
    return candidate if os.path.exists(candidate) else None


def optimize_apk(apk_path: str, log=print) -> str:
    """Return a smaller signed APK path, or the original path on any failure."""
    if not os.path.exists(apk_path):
        return apk_path
    tools = _build_tools()
    keystore = _debug_keystore()
    if not tools or not keystore:
        log("تعذر تجريد APK: build-tools أو debug.keystore غير موجود.")
        return apk_path

    original_size = os.path.getsize(apk_path)
    base = apk_path[:-4] if apk_path.lower().endswith(".apk") else apk_path
    stripped_zip = base + ".stripped.zip"
    aligned_apk = base + ".aligned.apk"
    signed_apk = base + ".signed.apk"

    try:
        log("[APK] جاري تجريد رموز debug من مكتبات APK...")
        with zipfile.ZipFile(apk_path, "r") as source, zipfile.ZipFile(stripped_zip, "w", zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                name = info.filename
                if name.startswith("META-INF/") and name.upper().endswith((".RSA", ".DSA", ".EC", ".SF", ".MF")):
                    continue
                data = source.read(name)
                if name.startswith("lib/") and name.endswith(".so"):
                    stripped = elf_strip.strip_elf(data)
                    if len(stripped) < len(data):
                        data = stripped
                target.writestr(info, data)

        zipalign = os.path.join(tools, "zipalign.exe")
        apksigner = os.path.join(tools, "apksigner.bat")
        align = subprocess.run(
            [zipalign, "-f", "-p", "4", stripped_zip, aligned_apk],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if align.returncode != 0:
            log(f"تعذر zipalign: {(align.stdout or align.stderr).strip()[:200]}")
            return apk_path

        env = os.environ.copy()
        jdk = paths.jdk_home()
        if jdk:
            env["JAVA_HOME"] = jdk
            env["PATH"] = os.path.join(jdk, "bin") + ";" + env.get("PATH", "")
        sign = subprocess.run(
            [
                apksigner, "sign",
                "--ks", keystore,
                "--ks-pass", "pass:android",
                "--key-pass", "pass:android",
                "--ks-key-alias", "androiddebugkey",
                "--out", signed_apk,
                aligned_apk,
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=180,
        )
        if sign.returncode != 0:
            log(f"تعذر إعادة توقيع APK: {(sign.stdout or sign.stderr).strip()[:200]}")
            return apk_path

        if not os.path.exists(signed_apk):
            return apk_path
        new_size = os.path.getsize(signed_apk)
        if new_size >= original_size:
            return apk_path
        log(
            f"[APK] تم تجريد APK: {round(original_size / 1024 / 1024, 1)} MB → "
            f"{round(new_size / 1024 / 1024, 1)} MB"
        )
        return signed_apk
    except Exception as exc:
        log(f"تعذر تحسين APK: {exc}")
        return apk_path
    finally:
        for temp in (stripped_zip, aligned_apk):
            try:
                if os.path.exists(temp):
                    os.remove(temp)
            except Exception:
                pass
