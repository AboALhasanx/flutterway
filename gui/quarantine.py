"""Quarantine instead of delete.

Every removal moves the folder into ``%LOCALAPPDATA%/FlutterWay/quarantine``
with a manifest, so a student can restore it.  Final deletion requires an
explicit ``DELETE <id>`` confirmation.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

try:
    from gui import paths
except ImportError:  # pragma: no cover
    import paths


def quarantine_root() -> Path:
    path = Path(paths.data_dir()) / "quarantine"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _same_volume(first: str, second: str) -> bool:
    return os.path.splitdrive(os.path.abspath(first))[0].lower() == os.path.splitdrive(
        os.path.abspath(second)
    )[0].lower()


def _tree_stats(root: str) -> tuple[int, int]:
    files = 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not os.path.islink(os.path.join(dirpath, name))]
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                continue
            try:
                total += os.path.getsize(full)
                files += 1
            except OSError:
                pass
    return files, total


def _inside(path: str, roots: list[str]) -> bool:
    resolved = os.path.normcase(os.path.realpath(os.path.abspath(path)))
    for root in roots:
        if not root:
            continue
        base = os.path.normcase(os.path.realpath(os.path.abspath(root)))
        if resolved == base:
            return False  # never remove the root itself
        try:
            if os.path.commonpath([resolved, base]) == base:
                return True
        except ValueError:
            continue
    return False


def list_items() -> list[dict]:
    items: list[dict] = []
    root = quarantine_root()
    for entry in sorted(root.iterdir(), reverse=True):
        manifest = entry / "manifest.json"
        if not entry.is_dir() or not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        data["id"] = entry.name
        data["quarantine_path"] = str(entry)
        items.append(data)
    return items


def quarantine(path: str, reason: str, allowed_roots: list[str]) -> dict:
    source = os.path.abspath(path or "")
    if not source or not os.path.isdir(source):
        return {"success": False, "error": "المجلد غير موجود."}
    if os.path.islink(source):
        return {"success": False, "error": "لا ننقل روابط رمزية."}
    if not _inside(source, allowed_roots):
        return {"success": False, "error": "المسار خارج النطاق المسموح."}
    item_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    target = quarantine_root() / item_id
    payload = target / "payload" / os.path.basename(source.rstrip("\\/"))
    try:
        payload.parent.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return {"success": False, "error": "معرّف الحجر مستخدم بالفعل."}

    files, size = _tree_stats(source)
    manifest = {
        "schema": 1,
        "id": item_id,
        "reason": str(reason or "manual")[:120],
        "original_path": source,
        "restore_to": source,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "size_bytes": size,
        "file_count": files,
    }
    try:
        if _same_volume(source, str(target)):
            shutil.move(source, str(payload))
        else:
            shutil.copytree(source, str(payload), symlinks=True)
            copied_files, copied_size = _tree_stats(str(payload))
            if (copied_files, copied_size) != (files, size):
                shutil.rmtree(target, ignore_errors=True)
                return {"success": False, "error": "فشل التحقق من النسخة؛ لم نحذف الأصل."}
            shutil.rmtree(source)
    except Exception as exc:
        shutil.rmtree(target, ignore_errors=True)
        return {"success": False, "error": f"تعذر نقل المجلد إلى الحجر: {exc}"}

    try:
        if _tree_stats(str(payload)) != (files, size):
            return {"success": False, "error": "النسخة في الحجر لا تطابق الأصل؛ الأصل محفوظ."}
    except Exception:
        pass

    part = target / "manifest.json.tmp"
    try:
        part.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(part, target / "manifest.json")
    except Exception as exc:
        return {"success": False, "error": f"نُقل المجلد لكن تعذر كتابة البيان: {exc}"}
    return {"success": True, "id": item_id, "manifest": manifest, "path": str(target)}


def _resolve(item_id: str) -> Path | None:
    root = quarantine_root()
    candidate = root / str(item_id or "")
    try:
        if candidate.parent != root or not candidate.is_dir():
            return None
    except Exception:
        return None
    return candidate


def restore(item_id: str, destination: str | None = None) -> dict:
    entry = _resolve(item_id)
    if entry is None:
        return {"success": False, "error": "عنصر الحجر غير موجود."}
    try:
        manifest = json.loads((entry / "manifest.json").read_text(encoding="utf-8"))
    except Exception:
        return {"success": False, "error": "بيان الحجر غير صالح."}
    payload = entry / "payload"
    children = list(payload.iterdir()) if payload.is_dir() else []
    if len(children) != 1:
        return {"success": False, "error": "محتوى الحجر غير متوقع."}
    source = children[0]
    target = os.path.abspath(destination or manifest.get("restore_to") or "")
    if not target:
        return {"success": False, "error": "لا يوجد مسار استعادة."}
    if os.path.exists(target) and (not os.path.isdir(target) or os.listdir(target)):
        return {"success": False, "error": "وجهة الاستعادة موجودة وغير فارغة."}
    try:
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        if _same_volume(str(source), target):
            shutil.move(str(source), target)
        else:
            shutil.copytree(str(source), target, symlinks=True)
            shutil.rmtree(source)
    except Exception as exc:
        return {"success": False, "error": f"تعذر الاستعادة: {exc}"}
    files, size = _tree_stats(target)
    if (files, size) != (manifest.get("file_count"), manifest.get("size_bytes")):
        return {"success": False, "error": "تم النسخ لكن التحقق من العدد/الحجم فشل.", "path": target}
    shutil.rmtree(entry, ignore_errors=True)
    return {"success": True, "path": target, "file_count": files, "size_bytes": size}


def purge(item_id: str, confirmation: str) -> dict:
    entry = _resolve(item_id)
    if entry is None:
        return {"success": False, "error": "عنصر الحجر غير موجود."}
    if str(confirmation or "").strip() != f"DELETE {item_id}":
        return {"success": False, "error": f"تأكيد مطلوب: اكتب DELETE {item_id}"}
    try:
        shutil.rmtree(entry)
    except Exception as exc:
        return {"success": False, "error": f"تعذر الحذف النهائي: {exc}"}
    return {"success": True, "id": item_id}
