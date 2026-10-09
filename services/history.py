"""Historique des téléchargements (bibliothèque)."""
import os
import uuid
from datetime import datetime
from pathlib import Path

from .paths import data_dir
from .storage import load_json, save_json


class History:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "history.json"
        self.entries: list[dict] = load_json(self.path, [])

    def add(self, *, title, url, file="", status="done", fmt="", project="", size=0, info=None) -> dict:
        entry = {
            "id": uuid.uuid4().hex[:12],
            "title": title, "url": url, "file": file, "status": status,
            "format": fmt, "project": project, "size": size, "info": info or {},
            "date": datetime.now().isoformat(timespec="seconds"),
        }
        self.entries.insert(0, entry)
        self.save()
        return entry

    def remove(self, entry_id: str):
        """Supprime l'entrée sans toucher au fichier."""
        self.entries = [e for e in self.entries if e["id"] != entry_id]
        self.save()

    def clear(self):
        self.entries = []
        self.save()

    def search(self, query: str = "", project: str = "") -> list[dict]:
        q = query.lower().strip()
        return [e for e in self.entries
                if (not q or q in e["title"].lower())
                and (not project or e.get("project") == project)]

    def find_existing(self, url: str, fmt: str) -> dict | None:
        """Fichier déjà téléchargé (même lien, même format, fichier encore présent)."""
        for e in self.entries:
            if e["url"] == url and e["format"] == fmt and e["status"] == "done" \
                    and e["file"] and os.path.exists(e["file"]):
                return e
        return None

    def save(self):
        save_json(self.path, self.entries)
