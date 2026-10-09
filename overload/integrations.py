"""Best-effort OS launch helpers for folders, default apps, and video editors."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

EDITOR_INFO = {
    "premiere": {"label": "Adobe Premiere Pro", "commands": ("premiere", "Adobe Premiere Pro")},
    "resolve": {"label": "DaVinci Resolve", "commands": ("resolve", "DaVinci Resolve")},
    "capcut": {"label": "CapCut", "commands": ("capcut", "CapCut")},
}


def _windows_editor_candidates(editor: str) -> list[Path]:
    program_dirs = [Path(value) for value in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")) if value]
    local = Path(os.environ.get("LOCALAPPDATA", "")) if os.environ.get("LOCALAPPDATA") else None
    candidates: list[Path] = []
    if editor == "premiere":
        for base in program_dirs:
            candidates.extend(base.glob("Adobe/Adobe Premiere Pro*/Adobe Premiere Pro.exe"))
            candidates.extend(base.glob("Adobe/Premiere Pro*/Adobe Premiere Pro.exe"))
    elif editor == "resolve":
        for base in program_dirs:
            candidates.extend(base.glob("Blackmagic Design/DaVinci Resolve/Resolve.exe"))
    elif editor == "capcut":
        if local:
            candidates.extend(local.glob("CapCut/Apps/*/CapCut.exe"))
            candidates.extend(local.glob("Programs/CapCut/CapCut.exe"))
        for base in program_dirs:
            candidates.extend(base.glob("CapCut/Apps/*/CapCut.exe"))
            candidates.extend(base.glob("CapCut/CapCut.exe"))
    return [path for path in candidates if path.is_file()]


def _mac_editor_candidate(editor: str) -> Path | None:
    names = {
        "premiere": ("Adobe Premiere Pro", "Adobe Premiere Pro 2025", "Adobe Premiere Pro 2026"),
        "resolve": ("DaVinci Resolve",),
        "capcut": ("CapCut",),
    }[editor]
    roots = [Path("/Applications"), Path.home() / "Applications"]
    for root in roots:
        for name in names:
            direct = root / f"{name}.app"
            if direct.exists():
                return direct
        for path in root.glob("Adobe Premiere Pro*.app") if editor == "premiere" else []:
            if path.exists():
                return path
    return None


def find_editor(editor: str) -> Path | str | None:
    if editor not in EDITOR_INFO:
        return None
    if sys.platform == "win32":
        candidates = _windows_editor_candidates(editor)
        return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[0] if candidates else None
    if sys.platform == "darwin":
        return _mac_editor_candidate(editor)
    for command in EDITOR_INFO[editor]["commands"]:
        executable = shutil.which(command)
        if executable:
            return executable
    return None


def editor_status() -> list[dict[str, Any]]:
    results = []
    for key, info in EDITOR_INFO.items():
        target = find_editor(key)
        results.append({"id": key, "label": info["label"], "installed": bool(target)})
    return results


def open_path(path: str | Path) -> tuple[bool, str]:
    path = Path(path).resolve()
    if not path.exists():
        return False, "Le chemin n'existe plus."
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            opener = shutil.which("xdg-open")
            if not opener:
                return False, "Aucune application système ne permet d'ouvrir ce chemin."
            subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Ouverture demandée au système."
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Impossible d'ouvrir ce chemin : {exc}"


def open_in_editor(editor: str, file_path: str | Path) -> tuple[bool, str]:
    if editor not in EDITOR_INFO:
        return False, "Logiciel de montage inconnu."
    file_path = Path(file_path).resolve()
    if not file_path.is_file():
        return False, "Le fichier n'existe plus."
    target = find_editor(editor)
    if not target:
        return False, f"{EDITOR_INFO[editor]['label']} n'a pas été détecté sur cet ordinateur."
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", str(target), "--args", str(file_path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen([str(target), str(file_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, f"Ouverture demandée à {EDITOR_INFO[editor]['label']}. Selon sa version, confirme l'import dans le logiciel."
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Impossible de lancer {EDITOR_INFO[editor]['label']} : {exc}"
