"""Paramètres utilisateur, stockés dans le dossier de données (préservés lors des mises à jour)."""
import copy
from pathlib import Path

from .paths import data_dir, default_download_dir
from .storage import load_json, save_json

DEFAULTS = {
    "download_dir": default_download_dir(),
    "default_quality": "best",        # "best" ou une hauteur ("1080", "720"...)
    "default_format": "mp4",          # mp4 | original | mp3 | wav
    "max_concurrent": 2,
    "fragments": 0,                   # connexions par fichier, 0 = auto
    "speed_limit": 0,                 # Mo/s, 0 = illimité
    "theme": "dark",
    "language": "fr",
    "notifications": True,
    "check_updates": True,
    "organize_by": "project",         # project | source | none
    "name_template": "%(title)s",
    "projects": [],                   # [{"name":..., "folder":...}]
    "current_project": "",
    "stats": {"done": 0, "failed": 0, "bytes": 0, "seconds": 0.0},
}


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "settings.json"
        stored = load_json(self.path, {})
        self.data = {**copy.deepcopy(DEFAULTS), **{k: v for k, v in stored.items() if k in DEFAULTS}}

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key, value, save=True):
        self.data[key] = value
        if save:
            self.save()

    def save(self):
        save_json(self.path, self.data)

    # --- Projets (Mode Monteur) ---
    def projects(self) -> list[dict]:
        return list(self.data["projects"])

    def add_project(self, name: str, folder: str) -> bool:
        name = name.strip()
        if not name or any(p["name"].lower() == name.lower() for p in self.data["projects"]):
            return False
        self.data["projects"].append({"name": name, "folder": folder})
        self.save()
        return True

    def remove_project(self, name: str):
        self.data["projects"] = [p for p in self.data["projects"] if p["name"] != name]
        if self.data["current_project"] == name:
            self.data["current_project"] = ""
        self.save()

    def project_folder(self, name: str) -> str | None:
        for p in self.data["projects"]:
            if p["name"] == name:
                return p["folder"]
        return None
