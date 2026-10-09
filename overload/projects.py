"""Project folders, safe media paths, and a small JSON asset manifest."""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_LAYOUT = (
    "Media/Video",
    "Media/Audio",
    "Media/Images",
    "Converted",
    "Exports",
    "Needs review",
    ".incoming",
)
PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_filename(value: str) -> str:
    """Return a single safe filename component, retaining useful Unicode text."""
    value = str(value or "media").replace("\\", "/").split("/")[-1]
    value = "".join(char for char in value if ord(char) >= 32 and char not in '<>:"|?*')
    value = value.strip().rstrip(". ")
    if value in {"", ".", ".."}:
        value = "media"
    if len(value) > 180:
        suffix = Path(value).suffix[:20]
        stem = value[:-len(suffix)] if suffix else value
        value = stem[: max(1, 180 - len(suffix))] + suffix
    if Path(value).stem.upper() in WINDOWS_RESERVED:
        value = f"_{value}"
    return value


def unique_filename(directory: Path, desired_name: str) -> str:
    """Choose a non-existing name for display/planning purposes."""
    desired_name = safe_filename(desired_name)
    stem, suffix = Path(desired_name).stem, Path(desired_name).suffix
    candidate = desired_name
    counter = 2
    while (directory / candidate).exists():
        candidate = f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


def reserve_unique_path(directory: Path, desired_name: str) -> Path:
    """Atomically reserve a collision-free path before moving a large media file."""
    directory.mkdir(parents=True, exist_ok=True)
    desired_name = safe_filename(desired_name)
    stem, suffix = Path(desired_name).stem, Path(desired_name).suffix
    counter = 1
    while True:
        name = desired_name if counter == 1 else f"{stem}_{counter}{suffix}"
        candidate = directory / name
        try:
            descriptor = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            return candidate
        except FileExistsError:
            counter += 1


class ProjectStore:
    def __init__(self, data_dir: str | Path | None = None):
        if data_dir is None:
            data_dir = os.environ.get("OVERLOAD_HOME") or (Path.home() / ".overload")
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.projects_dir = self.data_dir / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _slug(name: str) -> str:
        normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
        slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
        return (slug or "projet")[:42].rstrip("-")

    def create_project(self, name: str) -> dict[str, Any]:
        clean_name = " ".join(str(name).split())[:100]
        if not clean_name:
            raise ValueError("Le nom du projet est obligatoire.")
        with self._lock:
            while True:
                project_id = f"{self._slug(clean_name)}-{secrets.token_hex(3)}"
                root = self.projects_dir / project_id
                if not root.exists():
                    break
            root.mkdir(parents=True, exist_ok=False)
            for relative in PROJECT_LAYOUT:
                (root / relative).mkdir(parents=True, exist_ok=True)
            manifest = {
                "schema_version": 1,
                "id": project_id,
                "name": clean_name,
                "created_at": utc_now(),
                "assets": [],
            }
            self._write_manifest(root, manifest)
            return {key: manifest[key] for key in ("id", "name", "created_at")}

    def list_projects(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        with self._lock:
            for root in self.projects_dir.iterdir():
                if not root.is_dir() or not PROJECT_ID_RE.fullmatch(root.name):
                    continue
                try:
                    manifest = self._read_manifest(root)
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                projects.append({
                    "id": manifest.get("id", root.name),
                    "name": manifest.get("name", root.name),
                    "created_at": manifest.get("created_at"),
                    "asset_count": len(manifest.get("assets", [])),
                })
        return sorted(projects, key=lambda project: project.get("created_at") or "", reverse=True)

    def get_project(self, project_id: str) -> dict[str, Any]:
        root = self.project_path(project_id)
        manifest = self._read_manifest(root)
        if manifest.get("id") != project_id:
            raise FileNotFoundError("Projet introuvable.")
        return manifest

    def project_path(self, project_id: str) -> Path:
        if not PROJECT_ID_RE.fullmatch(str(project_id)):
            raise FileNotFoundError("Projet introuvable.")
        root = (self.projects_dir / project_id).resolve()
        if not root.is_relative_to(self.projects_dir.resolve()) or not root.is_dir():
            raise FileNotFoundError("Projet introuvable.")
        return root

    def list_assets(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            manifest = self.get_project(project_id)
            assets = []
            for asset in manifest.get("assets", []):
                relative = asset.get("relative_path")
                try:
                    path = self.safe_asset_path(project_id, relative)
                except (FileNotFoundError, ValueError, TypeError):
                    continue
                entry = dict(asset)
                try:
                    stat = path.stat()
                    entry["stale"] = (stat.st_size != asset.get("size_bytes") or
                                      stat.st_mtime_ns != asset.get("modified_ns"))
                except OSError:
                    entry["stale"] = True
                assets.append(entry)
            return sorted(assets, key=lambda asset: asset.get("added_at", ""), reverse=True)

    def safe_asset_path(self, project_id: str, relative_path: str) -> Path:
        if not isinstance(relative_path, str) or not relative_path or "\x00" in relative_path:
            raise ValueError("Chemin de fichier invalide.")
        root = self.project_path(project_id).resolve()
        candidate = (root / relative_path).resolve()
        if candidate == root or not candidate.is_relative_to(root):
            raise ValueError("Le chemin demandé sort du dossier du projet.")
        if not candidate.is_file():
            raise FileNotFoundError("Fichier introuvable dans le projet.")
        return candidate

    def add_asset(
        self,
        project_id: str,
        file_path: str | Path,
        analysis: dict[str, Any],
        *,
        role: str = "source",
    ) -> dict[str, Any]:
        root = self.project_path(project_id).resolve()
        path = Path(file_path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Le fichier doit se trouver dans le dossier du projet.")
        relative = path.relative_to(root).as_posix()
        stat = path.stat()
        entry = {
            "relative_path": relative,
            "filename": path.name,
            "role": role,
            "media_type": analysis.get("media_type", "unknown"),
            "size_bytes": stat.st_size,
            "modified_ns": stat.st_mtime_ns,
            "added_at": utc_now(),
            "analysis": analysis,
        }
        with self._lock:
            manifest = self.get_project(project_id)
            assets = [asset for asset in manifest.get("assets", []) if asset.get("relative_path") != relative]
            assets.append(entry)
            manifest["assets"] = assets
            self._write_manifest(root, manifest)
        return entry

    def update_asset_analysis(self, project_id: str, relative_path: str, analysis: dict[str, Any]) -> dict[str, Any]:
        path = self.safe_asset_path(project_id, relative_path)
        root = self.project_path(project_id)
        relative = path.relative_to(root).as_posix()
        with self._lock:
            manifest = self.get_project(project_id)
            for asset in manifest.get("assets", []):
                if asset.get("relative_path") == relative:
                    asset["analysis"] = analysis
                    stat = path.stat()
                    asset["size_bytes"] = stat.st_size
                    asset["modified_ns"] = stat.st_mtime_ns
                    asset["filename"] = path.name
                    asset["checked_at"] = utc_now()
                    asset["media_type"] = analysis.get("media_type", asset.get("media_type", "unknown"))
                    self._write_manifest(root, manifest)
                    return dict(asset)
        return self.add_asset(project_id, path, analysis)

    def relocate_asset(self, project_id: str, relative_path: str, destination_folder: str,
                       analysis: dict[str, Any]) -> dict[str, Any]:
        allowed_folders = {"Media/Video", "Media/Audio", "Media/Images", "Converted", "Needs review"}
        if destination_folder not in allowed_folders:
            raise ValueError("Dossier de destination invalide.")
        root = self.project_path(project_id)
        destination_dir = root / destination_folder
        destination_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            manifest = self.get_project(project_id)
            asset = next((item for item in manifest.get("assets", []) if item.get("relative_path") == relative_path), None)
            if asset is None:
                raise FileNotFoundError("Média introuvable dans le manifeste.")
            source = self.safe_asset_path(project_id, relative_path)
            if source.parent.resolve() == destination_dir.resolve():
                destination = source
            else:
                destination = reserve_unique_path(destination_dir, source.name)
                try:
                    os.replace(source, destination)
                except OSError:
                    destination.unlink(missing_ok=True)
                    raise
            stat = destination.stat()
            asset["relative_path"] = destination.relative_to(root).as_posix()
            asset["filename"] = destination.name
            asset["media_type"] = analysis.get("media_type", asset.get("media_type", "unknown"))
            asset["size_bytes"] = stat.st_size
            asset["modified_ns"] = stat.st_mtime_ns
            asset["analysis"] = analysis
            asset["checked_at"] = utc_now()
            self._write_manifest(root, manifest)
            return dict(asset)

    def _read_manifest(self, root: Path) -> dict[str, Any]:
        with (root / "project.json").open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, dict) or not isinstance(data.get("assets", []), list):
            raise ValueError("Manifeste de projet invalide.")
        return data

    @staticmethod
    def _write_manifest(root: Path, manifest: dict[str, Any]) -> None:
        temporary = root / ".project.json.tmp"
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, root / "project.json")
