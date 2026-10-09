"""Emplacements des fichiers de l'application."""
import os
import sys
from pathlib import Path


def resource(*parts) -> Path:
    """Chemin d'une ressource (compatible PyInstaller)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath(*parts)


def data_dir() -> Path:
    """Dossier des données utilisateur (conservé lors des mises à jour)."""
    override = os.environ.get("OVERLOAD_DATA_DIR")
    if override:
        p = Path(override)
    elif os.name == "nt":
        p = Path(os.environ.get("APPDATA", Path.home())) / "OverLoad"
    else:
        p = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "OverLoad"
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_download_dir() -> str:
    return str(Path.home() / "Downloads" / "OverLoad")
